# COLDGUARD — HỆ THỐNG BẢO VỆ CHUỖI LẠNH CHỦ ĐỘNG
## Project Scope · Architecture Baseline · AIoT Cyber-Physical Foundations

> **Document:** `docs/00-project-scope-architecture.md`  
> **Course:** Internet of Things (IoT) — Course Project / Bài tập lớn  
> **Project:** **ColdGuard — Hệ thống bảo vệ chuỗi lạnh chủ động**  
> **Type:** Project Charter + Research Baseline + Architecture Baseline + Internal RFC  
> **Status:** **PROPOSED FREEZE v1.0 — REVIEW CANDIDATE**  
> **Baseline date:** **2026-09-29**  
> **Team:** **4 members**  
> **Planning horizon:** **24 weeks**  
> **Normative role:** source of truth for project thesis, research questions, scope, physical-system boundary, exact purchased-hardware baseline, subsystem decomposition, authority boundaries, technology families, failure assumptions, quality goals, core architecture decisions, non-goals, project-level risk model and downstream-document hierarchy.  
> **Downstream documents:**  
> `01-physical-measurement-correctness-contract.md` → physical vocabulary, measurement semantics, exact electrical/thermal invariants, hardware integration and correctness contracts.  
> `02-aiot-closed-loop-engineering.md` → firmware, telemetry, MQTT, backend/twin, inference, command, closed-loop and recovery engineering.  
> `03-verification-experiments-demo.md` → commissioning proof, tests, experiment protocol, A/B, ablation, statistics, evidence and demo/defense contract.  
> `04-team-execution-plan.md` → 24-week chronology, ownership, dependencies, gates, integration and team review.  
> `05A/05B/05C/05D` → individual chronological execution playbooks.  
> **Hardware authority:** the 24-item purchased BOM frozen in §3 is authoritative. No downstream document, implementation shortcut or agent may silently replace, duplicate, omit or “upgrade” a core hardware item.  
> **Executable source of truth:** after an approved freeze, exact source code, pin definitions, schemas, migrations, broker configuration, container configuration, model artifacts and executable tests win over prose for patch-level implementation details only. If executable behavior changes a semantic rule or hardware assumption in this document, the document must be changed in the same reviewed change.  
> **Change policy:** changing the purchased BOM, physical testbed boundary, primary sensing set, cooling actuator, electrical-observation path, edge-controller role, research question, core/conditional scope, AI/control boundary, safety hierarchy, communication family, persistence family or evaluation claim requires project-level review and an update to this document before or together with implementation.

> **Project thesis.**  
> **ColdGuard is not a temperature dashboard with an AI label. It is a low-cost AIoT cyber-physical research testbed whose central question is whether multivariate thermal state and actuator telemetry can identify an impending thermal problem early enough to justify a safe physical intervention, then prove through electrical and thermal feedback that the intervention actually happened and improved a measurable physical outcome relative to a reactive baseline.**

---

# 0. Executive baseline

## 0.1 The problem we are actually solving

A conventional cold-chain monitoring prototype often stops at:

```text
temperature sensor
→ Wi-Fi
→ cloud/database
→ dashboard
→ threshold alarm
```

That architecture is useful for visibility, but it answers mainly:

> **“What is the temperature now?”**

ColdGuard studies a harder cyber-physical question:

> **“What state is the thermal system moving toward, is the cooling path actually capable of responding, should the system intervene before the ordinary threshold fires, and can the physical response be verified rather than merely assumed?”**

The project therefore treats temperature as a **trajectory and spatial field proxy**, not only a scalar reading.

Two observations can have the same instantaneous mean temperature while representing different states:

```text
State A
Tmean = 7.2 °C
gradient small
door closed
dT/dt ≈ 0
cooling response healthy
→ stable

State B
Tmean = 7.2 °C
gradient increasing
door recently open
dT/dt > 0
cooling effort present but recovery weak
→ deteriorating trajectory
```

A system that looks only at:

```text
T > threshold ?
```

cannot distinguish these states until later.

ColdGuard therefore adopts the following end-to-end reasoning loop:

```text
MEASURE
→ ESTIMATE STATE
→ PREDICT / DIAGNOSE
→ DECIDE
→ ACT
→ OBSERVE ELECTRICAL RESPONSE
→ OBSERVE THERMAL RESPONSE
→ VERIFY
→ UPDATE STATE
```

The final two steps are essential.

A command is not considered physically complete merely because:

```text
backend published MQTT command
```

or:

```text
ESP32 returned ACK
```

The project distinguishes at least:

```text
command requested
command accepted
command applied
electrical response observed
thermal response observed
physical outcome verified
```

This distinction is one of ColdGuard's main engineering contributions.

---

## 0.2 Why this is an IoT project rather than only an AI project

The project requires all of the following to work as one system:

```text
physical sensors
+
embedded acquisition
+
edge safety logic
+
wireless networking
+
IoT messaging
+
backend state
+
time-series evidence
+
predictive intelligence
+
policy
+
physical actuation
+
feedback verification
+
resilience
```

AI alone cannot make the project succeed.

If the predictive model is good but:

- sensor placement is unstable;
- time alignment is wrong;
- electrical feedback is untrustworthy;
- command replay is unsafe;
- actuator state is assumed rather than measured;
- experiments are not repeatable;

then the scientific claim is weak.

Likewise, a perfectly engineered IoT pipeline with no comparison against a reactive baseline does not establish the value of prediction.

ColdGuard is therefore intentionally a **system-level AIoT / cyber-physical project**.

---

## 0.3 Research question

### Central research question

> **Can a low-cost AIoT cyber-physical testbed use multi-point thermal sensing, environmental/event context and cooling-branch electrical telemetry to identify an impending thermal excursion before a reactive threshold controller, create a positive intervention window, perform a safety-bounded physical cooling action, and demonstrate through reproducible A/B experiments that at least one physical outcome improves?**

### RQ1 — Thermal observability

> Does multi-point sensing provide useful state information beyond a single temperature sensor?

Evidence family:

- `Tmax − Tmin`;
- spatial disagreement;
- recovery differences;
- single-sensor vs three-sensor ablation.

### RQ2 — Early predictive usefulness

> Can past-only temporal features and a practical ML model identify impending critical thermal state earlier than threshold/hysteresis monitoring on held-out independent runs?

Evidence family:

- Early Warning Lead Time;
- missed-event rate;
- false-warning rate;
- PR-oriented discrimination metrics;
- grouped evaluation by experiment run.

### RQ3 — Actuator observability and diagnosis

> Does adding command + cooling-branch current/power + thermal response improve the ability to distinguish “cooling requested” from “cooling physically effective”?

Evidence family:

```text
command ON + current present + thermal recovery
→ verified cooling response

command ON + current absent/near-zero
→ electrical/actuation response problem

command ON + current present + weak thermal response
→ degraded thermal effectiveness candidate
```

ColdGuard must not infer a component-specific root cause that the available sensors cannot prove.

### RQ4 — Closed-loop intervention

> Under matched disturbances, does predictive intervention improve at least one physical outcome relative to reactive threshold control?

Primary physical outcomes:

- thermal exposure;
- recovery time;
- critical excursion occurrence/severity.

### RQ5 — Resilience

> Can basic thermal protection remain available when backend, broker or predictive inference is unavailable?

Core evidence:

- `SAFE_LOCAL`;
- command rejection on stale/invalid state;
- reconnect/resynchronization behavior.

### RQ6 — Energy–thermal trade-off — conditional

> After the core closed loop is proven, can control reduce unnecessary cooling effort without worsening thermal safety outcomes?

**RQ6 is conditional/stretch.**

It is not allowed to delay:

- safe hardware;
- calibrated sensing;
- reactive baseline;
- predictive evaluation;
- verified closed loop.

---

## 0.4 Hypotheses

| ID | Hypothesis | Minimum acceptable evidence |
|---|---|---|
| **H1** | Multi-point thermal observation contains useful information beyond one temperature | A1 ablation shows measurable difference in state characterization and/or predictive usefulness |
| **H2** | Predictive state can create useful advance warning | held-out Early Warning Lead Time is positive for a meaningful fraction of valid events, with distribution/CI reported |
| **H3** | The warning is physically actionable | available lead time exceeds sensing + inference + decision + command + actuator/thermal response delay for a meaningful subset of events |
| **H4** | Predictive closed-loop intervention can improve a physical outcome | paired A/B experiment improves thermal exposure and/or recovery time without violating safety constraints |
| **H5** | Electrical actuator telemetry improves diagnosis/verification | thermal-only vs thermal+electrical ablation and controlled fault cases show additional discrimination/verification value |
| **H6** | Local deterministic fallback preserves minimum protection | network/backend loss experiment shows continued bounded local control and later resynchronization |
| **H7** | Energy-aware control may reduce cooling effort without harming thermal outcome | conditional experiment only after core gates pass |

No hypothesis pre-commits to a marketing-style number such as:

```text
AI accuracy = 95%
energy saving = 20%
```

before data exists.

Negative or neutral results are scientifically acceptable if the experiment is valid and the limitation is explained.

---

## 0.5 Architecture in one paragraph

ColdGuard uses a **6 L HS2 physical chamber** observed by **three waterproof 1 m DS18B20 probes**, one **3.3 V BME280 module** and one **MC-38 reed switch**. One controller on the purchased **dual ESP32-S3R2 + W25Q32 + CH343G board** acts as the primary edge controller. Cooling is produced by the purchased **single TEC1-12715 SKU** integrated with the **12 V Peltier thermal assembly V1** and driven through one **BTS7960 / IBT-2 H-bridge module**. The cooling branch is electrically observed by one **PZEM-017** configured for the purchased **50 A / 75 mV external shunt**, connected to the ESP32 through a purchased **3.3 V MAX3485 RS-485 module**. A **12 V / 33 A (~400 W) PSU**, ATO fuse box, selectable 10/15/20 A TEC fuses, ≥2 auxiliary 5 A fuses, **XL4015**, **TB4504**, **PCT218** and the frozen wire set provide power conversion, distribution and protection. The ESP32 publishes telemetry over Wi-Fi using MQTT/TLS to a backend that stores raw/time-series evidence, maintains a lightweight `reported / desired / derived` device-twin state, runs or consumes predictive inference, applies a safety-bounded policy and publishes commands. The device acknowledges execution, while PZEM electrical measurements and thermal sensors provide independent physical-response evidence. If backend/broker connectivity is unavailable, the ESP32 falls back to deterministic local threshold/hysteresis protection.

---

## 0.6 Scope baseline

### P0 — mandatory core

P0 is the smallest system that can support the central research claim.

```text
PHYSICAL TESTBED
- exact purchased 24-item BOM in §3
- one 6 L chamber
- one TEC cooling branch
- multi-point temperature observation
- environmental context
- door disturbance context
- cooling-branch electrical observation

EDGE
- one ESP32-S3R2 as primary controller
- deterministic sensing schedule
- sensor-quality checks
- command validation
- safe default-OFF actuation
- local fallback

IOT
- Wi-Fi
- MQTT
- TLS-capable deployment
- telemetry / event / state / command / ACK semantics
- reconnect/resynchronization

DATA
- raw telemetry retained
- experiment/run metadata
- device/twin state
- command and event audit
- model/policy/hardware/firmware provenance

PREDICTION
- threshold baseline
- threshold + hysteresis baseline
- XGBoost core predictive model
- past-only temporal features
- grouped evaluation by independent run
- probability calibration only if probability semantics are exposed

CONTROL
- Controller A: reactive threshold/hysteresis
- Controller B: predictive ColdGuard
- policy/safety gate between prediction and actuation
- command → electrical response → thermal response verification

RESILIENCE
- SAFE_LOCAL
- stale/invalid state handling
- backend/broker disconnect experiment

EVIDENCE
- commissioning evidence
- controlled disturbance runs
- A/B paired comparison
- ablation
- statistical uncertainty reporting
- reproducible demo
```

### P1 — conditional after core gates

Only after P0 is stable:

- multiple PWM operating levels;
- energy-aware duty policy;
- richer anomaly model;
- richer dashboard;
- additional diagnosis classes;
- optional product thermal proxy if separately approved;
- optional internal circulation fan if characterization proves it necessary;
- secure boot / flash encryption hardening;
- additional model families for comparison.

P1 may not require silent hardware substitution.

### P2 — explicitly out of scope for the baseline

- compressor-scale refrigeration claims;
- commercial cold-room performance claims;
- food-safety certification;
- universal remaining-shelf-life prediction;
- “freshness percentage” without biological ground truth;
- camera/computer vision;
- gas sensing not in the BOM;
- blockchain;
- reinforcement learning as core controller;
- GRU/LSTM/TCN/Transformer merely for novelty;
- CFD-grade Digital Twin;
- physics-informed neural network claim without a real physics-constrained model;
- Kubernetes;
- Kafka/Redpanda;
- microservice proliferation;
- multi-device fleet;
- second ESP32 used as an artificial distributed node without a requirement;
- production-scale HA/SLO claims.

**Scope principle:**

> Add complexity only when it closes a named research/engineering risk or produces evidence that cannot be obtained more simply.

---

## 0.7 Quality goals

| ID | Goal | Meaning | Acceptance signal |
|---|---|---|---|
| **Q1 Physical correctness** | physical state is measured and interpreted consistently | no hidden substitution between commanded and measured state | commissioning + response verification |
| **Q2 Safety** | actuation is bounded and fail-safe | default OFF, fuse protection, local fallback, no unsafe fault injection | safety tests |
| **Q3 Measurement quality** | sensor/electrical data are usable evidence | calibration, stable placement, quality flags, timestamp/run provenance | calibration/characterization report |
| **Q4 Predictive usefulness** | model adds useful lead time, not only offline score | held-out lead-time and false-warning evidence | RQ2 evaluation |
| **Q5 Closed-loop value** | prediction leads to a measurable physical effect | paired reactive/predictive experiments | RQ4 evidence |
| **Q6 Explainability** | each intervention can be reconstructed | telemetry + prediction + policy + command + ACK + physical response | event timeline |
| **Q7 Resilience** | minimum protection remains during cloud/network loss | SAFE_LOCAL experiment | recovery evidence |
| **Q8 Reproducibility** | another reviewer can reproduce the test | frozen config/version/run manifest | clean-run evidence |
| **Q9 Security baseline** | remote actuation is not trivially spoofable/replayed | identity, TLS path, ACL/authz, command freshness | negative tests |
| **Q10 Scope discipline** | complexity remains intentional | optional work blocked until core gates pass | gate review |

---

# 1. Real-world context and 2026 positioning

## 1.1 Why cold-chain monitoring is a defensible application domain

Temperature-controlled logistics is not a toy domain.

Vietnam's fruit-and-vegetable export value exceeded approximately **US$8.5 billion in 2025**, according to a December 2025 Government News report citing industry estimates.

FiinResearch's **Vietnam Cold Chain Market Report 2026** describes:

- approximately **US$388 million** cold-chain logistics market size in 2025;
- **78 commercial cold-storage providers**;
- more than **1.4 million designed pallet positions** by end-2025;
- 10.5% designed cold-storage capacity growth during 2023–2025.

These figures do **not** prove product-market fit for ColdGuard.

They justify only the following limited statement:

> temperature-controlled storage and transport are economically meaningful systems in Vietnam, so reliability, monitoring and efficient intervention are credible engineering problems.

---

## 1.2 Why “sensor + cloud dashboard” is not a 2026 novelty claim

Recent work already goes beyond threshold dashboards.

A 2026 Applied Sciences paper on refrigerated maritime containers explicitly describes common threshold alarm practice as reactive and proposes early anomaly detection using a hybrid Digital Twin plus deep learning.

A 2026 Frontiers review on digital twins for food processing/shelf-life emphasizes the combination of:

- sensors;
- mechanistic/data-driven models;
- near-real-time state estimation;
- prediction;
- uncertainty;
- decision support;
- domain validation.

A 2026 Sustainable Futures paper validates autonomous IoT-based temperature monitoring in a real food-supply-chain pilot.

Therefore ColdGuard must **not** claim novelty simply because it contains:

```text
ESP32
+ MQTT
+ Digital Twin
+ AI
```

Those ingredients are already established.

---

## 1.3 Where ColdGuard can legitimately contribute

ColdGuard's defensible contribution is a **student-scale systems contribution**:

```text
low-cost physical testbed
+
multi-point thermal observation
+
disturbance context
+
actuator electrical observability
+
predictive state
+
safety-bounded physical intervention
+
electrical verification
+
thermal verification
+
resilient local fallback
+
controlled A/B evidence
```

The project is **SOTA-oriented in architecture and methodology**, not an algorithmic-state-of-the-art claim.

---

## 1.4 Why the project does not claim shelf life

Thermal history influences quality, but:

```text
thermal exposure
≠
biological quality ground truth
```

The current purchased hardware does not directly measure:

- microbial load;
- ethylene;
- CO₂;
- firmness;
- soluble solids;
- color/freshness chemistry;
- initial biological condition.

Therefore the project may discuss:

```text
thermal condition
thermal risk
thermal exposure
equipment/cooling response
```

but must not report:

```text
fruit is 73% fresh
remaining shelf life = 4.2 days
food is safe
```

without an independently validated quality model and appropriate ground truth.

---

# 2. Cyber-physical foundations

## 2.1 The physical plant is part of the computation

ColdGuard has a physical feedback loop.

Conceptually:

```text
software action u(t)
        ↓
electrical plant
        ↓
TEC heat pumping
        ↓
thermal plant
        ↓
temperature state x(t)
        ↓
sensors
        ↓
software estimate
```

The system cannot be evaluated solely by software latency or classifier accuracy.

The plant's:

- thermal inertia;
- heat leakage;
- hot-side rejection;
- sensor placement;
- door disturbance;
- ambient condition;

directly affect the data-generating process.

---

## 2.2 Temperature is a field proxy, not one perfect scalar

Three DS18B20 sensors are retained because the chamber can have spatial differences.

Define:

\[
T_{\max}(t)=\max(T_1,T_2,T_3)
\]

\[
T_{\min}(t)=\min(T_1,T_2,T_3)
\]

\[
T_{\text{mean}}(t)=\frac{T_1+T_2+T_3}{3}
\]

\[
G_T(t)=T_{\max}(t)-T_{\min}(t)
\]

where:

- `T1` is near the door region;
- `T2` is central;
- `T3` is far from the door/opposite region;

subject to final physical placement freeze in Doc 01.

`G_T` is not a universal cold-chain quality metric.

It is a testbed state feature that can reveal:

- stratification;
- localized disturbance;
- uneven recovery;
- geometry repeatability problems.

---

## 2.3 Door state is causal context

A rising temperature without event context is ambiguous.

Example:

```text
temperature rising
```

could be caused by:

- door opening;
- cooling disabled;
- cooling degradation;
- ambient/load change;
- sensor problem.

Adding:

```text
Door = OPEN
```

provides context for a controlled disturbance.

The MC-38 therefore has high research ROI despite its simplicity.

---

## 2.4 Electrical response is actuator observability

Without current/power observation:

```text
command ON
```

does not tell the system whether power actually flowed to the cooling branch.

The PZEM path therefore creates a second observation channel:

```text
software intent
→ electrical effect
→ thermal effect
```

The project deliberately separates:

```text
COMMAND
ACK
ELECTRICAL RESPONSE
THERMAL RESPONSE
```

An ACK is protocol evidence.

PZEM is physical electrical evidence.

DS18B20 response is physical thermal evidence.

---

## 2.5 Verification is stronger than actuation

ColdGuard's main loop is not:

```text
predict → command
```

It is:

```text
predict
→ policy
→ command
→ ACK
→ observe I/P
→ observe temperature response
→ verify
```

This prevents a common IoT conceptual error:

> assuming a remote command equals a physical outcome.

---

## 2.6 Reactive control is not the enemy; it is the scientific baseline

A threshold/hysteresis controller is:

- deterministic;
- easy to audit;
- locally executable;
- robust under connectivity loss;
- a fair baseline.

ColdGuard must prove value **against** this baseline.

The project therefore keeps two controllers conceptually separate:

### Controller A — reactive

```text
measured state exceeds configured boundary
→ cooling action
```

### Controller B — predictive

```text
past-only state trajectory indicates impending critical state
→ policy checks
→ cooling action earlier than Controller A
```

If Controller B cannot improve a physical outcome, the project must report that honestly.

---

## 2.7 Predictive control must remain subordinate to safety

The hierarchy is:

```text
physical safety
>
hardware/electrical limits
>
local deterministic protection
>
fault/degraded handling
>
predictive optimization
>
energy optimization
```

AI is not an actuator authority.

It supplies:

```text
risk / prediction / diagnostic evidence
```

Policy decides whether an action is allowed.

---

## 2.8 Digital Twin boundary

ColdGuard uses a **lightweight testbed/device Digital Twin**, not a full commercial cold-chain Digital Twin.

Minimum state families:

```text
REPORTED
- what the physical device/sensors report

DESIRED
- what the backend/policy asks the device to do

DERIVED
- computed state, quality flags, features, risk, cooling-health interpretation
```

This follows a well-established IoT state-synchronization pattern similar to the `reported / desired / delta` concept used by AWS IoT Device Shadow, while ColdGuard implements only the subset needed for the project.

The twin is:

- a synchronized representation;
- an audit/decision support layer;

not:

- the physical authority;
- a CFD simulation;
- proof that an action occurred.

Physical response remains sensor-derived.

---

# 3. Exact purchased-hardware baseline

## 3.1 Hardware freeze rule

The following table is copied from the team's **current purchased-hardware freeze**.

This list is authoritative.

No architectural optimization in this document changes it.

### Current BOM — exact baseline

| ID | Purchased item | Frozen purchase specification | Quantity |
|---|---|---|---:|
| **HW-01** | Board điều khiển | **Dual ESP32-S3R2 + W25Q32 + CH343G** | **1** |
| **HW-02** | DS18B20 | **Waterproof, dây 1 m** | **3** |
| **HW-03** | BME280 | **I²C, module 3.3 V** | **1** |
| **HW-04** | MC-38 | **Reed switch** | **1** |
| **HW-05** | PZEM-017 | **RS485 / Modbus** | **1** |
| **HW-06** | Shunt | **50 A / 75 mV** | **1** |
| **HW-07** | MAX3485 | **Module RS485 3.3 V** | **1** |
| **HW-08** | BTS7960 / IBT-2 | **H-Bridge module** | **1** |
| **HW-09** | TEC1-12715 | **Đúng SKU / sản phẩm đã chọn** | **1** |
| **HW-10** | Bộ tản Peltier V1 | **12 V** | **1** |
| **HW-11** | Chamber | **HS2 6 L** | **1** |
| **HW-12** | PSU | **12 V / 33 A, khoảng 400 W** | **1** |
| **HW-13** | XL4015 | **DC-DC Buck** | **1** |
| **HW-14** | Fuse Box | **ATO 4-way** | **1** |
| **HW-15** | Fuse TEC | **Bộ 10 A / 15 A / 20 A** | **1 bộ** |
| **HW-16** | Fuse phụ | **5 A** | **≥2** |
| **HW-17** | TB4504 | **45 A 4P** | **1** |
| **HW-18** | PCT218 | **8 cổng** | **1** |
| **HW-19** | Dây công suất | **2×2.5 mm²** | **~2 m** |
| **HW-20** | Dây phụ | **2×0.75 mm²** | **~1 m** |
| **HW-21** | Jumper | **M-M / M-F / F-F** | **1 bộ** |
| **HW-22** | Header | **2.54 mm** | **đủ** |
| **HW-23** | Điện trở | **4.7 kΩ** | **≥1** |
| **HW-24** | Thermal paste | **Đi kèm bộ V1** | **đủ** |

---

## 3.2 No-substitution policy

The following are **not** allowed to happen silently:

```text
PZEM-017 → INA226
IBT-2 → discrete MOSFET stage
1 TEC → 2 TECs
6 L chamber → 20 L chamber
ESP32-S3R2 board → unrelated dev board
50 A shunt → other shunt range
12 V / 33 A PSU → different supply
```

If any physical item must change because of a verified hardware defect or incompatibility:

1. record the observed failure;
2. preserve measurement evidence;
3. review the impact on research comparability;
4. version the hardware configuration;
5. update Docs 00–03 before new experiment data are mixed with old data.

---

## 3.3 What is known from manufacturer documentation

### DS18B20

Analog Devices specifies:

- 1-Wire interface;
- multidrop capability;
- unique 64-bit ROM code;
- programmable 9–12 bit resolution;
- −55 °C to +125 °C measurement range;
- ±0.5 °C accuracy over −10 °C to +85 °C for the IC.

Project implication:

- three probes can share one 1-Wire bus;
- ROM IDs must be mapped permanently to T1/T2/T3 physical positions;
- waterproof-probe assembly accuracy must still be checked as an assembled product.

### BME280

Bosch specifies:

- I²C/SPI;
- VDD 1.71–3.6 V;
- VDDIO 1.2–3.6 V;
- temperature range −40…85 °C;
- typical humidity accuracy tolerance around ±3 %RH under specified conditions;
- humidity response time around 1 s.

Project implication:

- a 3.3 V module is logically compatible with ESP32;
- BME280 is context sensing, not a substitute for the three DS18B20 spatial probes.

### MAX3485

Analog Devices specifies MAX3485 as:

- 3.3 V powered;
- half-duplex RS-485/RS-422 transceiver;
- up to 10 Mbps for the MAX3485 family member;
- driver/receiver enable;
- logic interoperability with 5 V systems.

Project implication:

- 9600-baud PZEM communication is far below the transceiver bandwidth;
- the purchased module must be powered according to its 3.3 V design;
- wiring/pin labeling still follows the actual purchased module.

### ESP32-S3R2

Espressif's current ESP32-S3 Series Datasheet v2.2 states:

- ESP32-S3R2 contains **2 MB Quad SPI in-package PSRAM**;
- ESP32-S3R2 is now marked **EOL**, upgraded by Espressif to ESP32-S3RH2;
- this lifecycle status does not invalidate an already purchased board.

Espressif's GPIO documentation states that GPIO33–GPIO37 are additionally occupied for variants using **Octal** flash/PSRAM; the warning specifically applies to octal configurations such as S3R8/S3R8V rather than the S3R2's 2 MB Quad PSRAM configuration.

Project implication:

- the S3R2 itself does not create the same octal-PSRAM restriction on GPIO33–37;
- however the team's board is a custom dual-S3R2 board with W25Q32/CH343G, so **board-level schematic/routing remains the final pin-availability authority**;
- Doc 01 must verify final GPIO mapping against the actual board.

### BTS7960 silicon

Infineon's BTS7960 datasheet specifies the **chip**, not the whole IBT-2 module:

- integrated high-current half bridge;
- logic-level inputs;
- PWM operation up to 25 kHz;
- overtemperature/overvoltage/undervoltage/overcurrent/short-circuit protections;
- typical current-limitation level around 43 A under specified conditions.

Project implication:

> **43 A must not be documented as a guaranteed continuous-current rating of the purchased IBT-2 module.**

The module adds:

- PCB copper;
- terminals;
- solder;
- buffer logic;
- thermal path;
- possibly clone/surplus silicon.

Those module-level limits must be characterized empirically.

### PZEM-017

The available Peacefair-style PZEM-017 manual describes:

- RS-485;
- Modbus RTU;
- 9600 baud;
- 8 data bits;
- no parity;
- 50/100/200/300 A external-shunt profiles;
- `0x0001` profile value for 50 A range;
- voltage resolution 0.01 V;
- current resolution 0.01 A;
- power resolution 0.1 W;
- energy resolution 1 Wh;
- external 5 V (>100 mA) supply for the passive RS-485 communication interface.

Manual revisions in circulation disagree on 1 vs 2 stop bits.

Project implication:

- firmware serial format must be configurable during bring-up;
- the module shipped with the team is the final authority for revision-specific serial settings;
- 50 A shunt profile must be verified rather than assumed.

---

## 3.4 What is NOT allowed to be invented from generic datasheets

### TEC1-12715

The commercial name `TEC1-12715` is not treated as one immutable datasheet.

The project currently knows only:

```text
purchased SKU = the exact product selected by the team
quantity = 1
```

The following are commissioning-derived:

- actual dimensions;
- current at 12 V;
- input power;
- achievable cold-side response;
- hot-side response;
- stable operating region.

Generic Internet values such as:

```text
Imax = 15 A
Qmax = 150 W
Vmax = 15.4 V
```

may be used only as **external comparison context**, not as the measured specification of the team's module.

### V1 Peltier thermal assembly

The purchased V1 assembly is frozen.

Seller statements such as:

```text
supports TEC up to 150 W
```

are treated as seller ratings until experimentally verified.

### IBT-2 module

The actual module's:

- buffer IC;
- PCB;
- resistor values;
- thermal behavior;
- 3.3 V logic compatibility;

must be verified on the purchased unit.

Community reports show meaningful board-to-board/schematic variation among IBT-2 modules, reinforcing the need for commissioning rather than assuming every board matches one online schematic.

### Dual ESP32-S3R2 board

The chip family is documented by Espressif.

The team's exact dual-MCU board routing is not established by the chip datasheet.

Therefore:

```text
chip compatibility
≠
board pinout proof
```

---

## 3.5 System power sanity check

Main PSU frozen rating:

\[
V_{PSU}=12\text{ V}
\]

\[
I_{PSU,max}=33\text{ A}
\]

Ideal nameplate output:

\[
P_{PSU,max}=12\times33=396\text{ W}
\]

Therefore the project's phrase:

```text
approximately 400 W
```

is consistent.

This is capacity, not consumption.

The load determines actual current.

Illustrative electrical-input envelopes at 12 V:

| Cooling-branch current | Approx. electrical input |
|---:|---:|
| 5 A | 60 W |
| 10 A | 120 W |
| 12 A | 144 W |
| 15 A | 180 W |
| 20 A | 240 W |

These values are not TEC ratings.

They are simple `P = VI` planning points used to understand PSU headroom.

Even at 15 A:

\[
396-180=216\text{ W}
\]

of ideal nameplate capacity remains before auxiliary loads/losses.

Therefore the 12 V / 33 A supply is not expected to be the first bottleneck for one TEC.

The likely first system-level uncertainty is **thermal rejection**, not raw PSU nameplate wattage.

---

## 3.6 50 A / 75 mV shunt sanity check

Frozen shunt:

\[
50\text{ A} \rightarrow 75\text{ mV}
\]

Equivalent shunt resistance:

\[
R_s=\frac{0.075}{50}=0.0015\ \Omega=1.5\text{ m}\Omega
\]

Illustrative shunt drop/loss:

| Current | Shunt drop | Shunt dissipation |
|---:|---:|---:|
| 5 A | 7.5 mV | 0.0375 W |
| 10 A | 15 mV | 0.15 W |
| 15 A | 22.5 mV | 0.3375 W |
| 20 A | 30 mV | 0.60 W |

These values support the architectural use of the shunt as a low-insertion-loss measurement element for the expected one-TEC branch.

Final thermal/terminal behavior remains a commissioning item.

---

## 3.7 Thermal-system sanity check

A TEC is a heat pump.

Ferrotec's thermoelectric reference guidance emphasizes that the hot-side heat sink must reject:

```text
heat pumped from cold side
+
electrical/Joule heat
```

Therefore:

```text
cold-side success
```

cannot be evaluated without adequate hot-side heat rejection.

ColdGuard's architecture consequently treats:

```text
V1 hot-side assembly
+
fan
+
thermal contact
```

as part of the cooling plant, not an accessory.

---

## 3.8 Why the 6 L chamber changes the experimental design

Chamber volume:

\[
V=6\text{ L}=0.006\text{ m}^3
\]

Using a rough room-condition air density of approximately:

\[
\rho \approx 1.2\text{ kg/m}^3
\]

air mass alone is approximately:

\[
m_{air}\approx0.0072\text{ kg}
\]

With air specific heat around:

\[
c_p\approx1005\text{ J/(kg·K)}
\]

air-only sensible heat for a 10 K change is roughly:

\[
Q_{air}\approx0.0072\times1005\times10
\approx72\text{ J}
\]

This is deliberately an **order-of-magnitude illustration**, not a chamber cooling-load model.

Real testbed dynamics include:

- chamber walls;
- cold/hot plates;
- TEC assembly;
- sensor bodies;
- leakage/infiltration;
- moisture/condensation;
- door opening;
- internal contents;
- ambient coupling.

Architectural consequence:

> prediction horizon must be selected from measured plant dynamics, not inherited from the old 20 L / two-TEC design.

Hard-coding old 5/15/30-minute horizons before characterization is prohibited.

---

## 3.9 Sampling-rate sanity check

Baseline target:

```text
DS18B20       ≈ 1 Hz
BME280        ≈ 1 Hz
PZEM          ≈ 1–2 Hz
door          event-driven + sampled state
MQTT telemetry ≈ 1 Hz
commands      event-driven
```

Why 1 Hz is reasonable:

- the dominant plant dynamics are thermal, not audio/RF-rate;
- BME280 humidity response is on the order of one second;
- DS18B20 at maximum resolution has a conversion time on the order of hundreds of milliseconds;
- higher rates increase data redundancy without automatically increasing useful thermal information.

At 1 Hz:

\[
86,400\text{ telemetry samples/device/day}
\]

Assuming a serialized telemetry payload of approximately 0.5–1.0 KB:

\[
\approx43\text{–}86\text{ MB/day}
\]

before database/index/protocol overhead.

Even continuous collection from one device is not a throughput problem requiring Kafka, sharding or a distributed database.

The engineering challenge is:

- semantics;
- time alignment;
- provenance;
- quality;
- reproducibility;

not throughput scale.

---

## 3.10 PZEM energy semantics

PZEM energy resolution is coarse relative to short experiments:

```text
1 Wh
```

Therefore short-run research energy should use sampled power integration:

\[
E\approx\sum_i P_i\Delta t
\]

with the PZEM energy counter as a cross-check.

The project must not call the PZEM measurement:

```text
Total System Energy
```

because the measurement path is the **cooling branch**, while:

- ESP32;
- logic;
- some fan/auxiliary loads;

may not all be inside that measured branch.

Canonical wording:

```text
Cooling-branch Power
Cooling-branch Energy
```

---

## 3.11 PWM measurement caution

BTS7960 silicon supports switching far above the thermal plant's natural bandwidth.

That does **not** prove that:

```text
PZEM power reading under fast PWM
```

is already validated as a scientific energy metric.

The PZEM documentation does not provide sufficient detail about internal averaging under the team's exact PWM load waveform.

Therefore:

- core A/B control should be interpretable without requiring unvalidated PWM-energy semantics;
- PWM levels may be characterized experimentally;
- energy-aware PWM optimization remains conditional.

---

# 4. System architecture

## 4.1 Layer decomposition

```text
┌──────────────────────────────────────────────────────────────┐
│                     HUMAN / EXPERIMENT LAYER                 │
│  operator · experiment runner · dashboard · evidence review  │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                    APPLICATION / DECISION                    │
│ risk · diagnosis · policy · reactive/predictive controller   │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                   IOT BACKEND / DIGITAL TWIN                 │
│ ingestion · raw data · twin · events · commands · realtime   │
└──────────────────────────────┬───────────────────────────────┘
                               │ MQTT/TLS
┌──────────────────────────────▼───────────────────────────────┐
│                         EDGE DEVICE                          │
│ ESP32-S3R2 · sensing · validation · local state · SAFE_LOCAL │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
        sensing / RS485                    PWM/enable
                │                              │
┌───────────────▼──────────────────────────────▼───────────────┐
│                       PHYSICAL TESTBED                       │
│ T1/T2/T3 · BME280 · Door · PZEM · IBT-2 · TEC · V1 · HS2    │
└──────────────────────────────────────────────────────────────┘
```

---

## 4.2 Data flow

```text
DS18B20 ×3 ────────────────┐
BME280 ────────────────────┤
MC-38 ─────────────────────┤
PZEM-017 → MAX3485 ────────┤
                           ▼
                      ESP32-S3R2
                           │
                        MQTT/TLS
                           │
                           ▼
                         Broker
                           │
                           ▼
                  Ingestion / State
                    │      │       │
                    │      │       └→ Event / audit timeline
                    │      └────────→ Current twin
                    └───────────────→ Raw time-series
```

---

## 4.3 Decision/control flow

```text
raw + twin state
       │
       ▼
feature/state construction
       │
       ├────────→ deterministic baseline
       │
       └────────→ XGBoost / predictive risk
                         │
                         ▼
                  policy / safety gate
                         │
                         ▼
                    cooling command
                         │
                       MQTT
                         │
                         ▼
                      ESP32
                         │
                  validate/freshness
                         │
                         ▼
                       IBT-2
                         │
                         ▼
                         TEC
```

AI never bypasses policy/safety validation.

---

## 4.4 Verification flow

```text
CoolingCommand C
       │
       ▼
ESP accepts/applies
       │
       ├────────→ ACK / applied state
       │
       ▼
IBT-2 / TEC branch
       │
       ├────────→ PZEM: V/I/P
       │
       └────────→ chamber thermal response
                         │
                         ▼
                    DS18B20 ×3
                         │
                         ▼
                       VERIFY
```

---

## 4.5 Power flow

Architectural baseline:

```text
12 V / 33 A PSU
        │
      Fuse Box
        │
        ├──────── TEC branch
        │          │
        │      selected TEC fuse
        │          │
        │        IBT-2
        │          │
        │         TEC
        │          │
        │    return via 50 A shunt
        │
        ├──────── V1 fan branch
        │          │
        │        5 A fuse
        │
        └──────── logic branch
                   │
                 5 A fuse
                   │
                 XL4015
                   │
                   └→ 5 V logic / PZEM communication side
```

Exact wiring is downstream Doc 01 authority.

---

## 4.6 Thermal flow

```text
chamber air/load
      ↓
cold-side assembly
      ↓
TEC
      ↓
hot-side assembly
      ↓
fan
      ↓
ambient
```

A TEC does not create “cold”.

It moves heat while also adding electrical input that ultimately must be rejected on the hot side.

---

## 4.7 Authority boundaries

| Fact | Authority / strongest evidence |
|---|---|
| physical T1/T2/T3 readings | device telemetry from mapped physical sensors |
| door state | MC-38 device input |
| branch V/I/P | PZEM measurement path |
| requested action | backend desired command/audit |
| device accepted/applied action | device reported/ACK state |
| current physical electrical response | PZEM |
| current thermal response | temperature telemetry |
| predictive risk | versioned model/inference result |
| actuation permission | policy/safety layer |
| fallback action during cloud loss | ESP32 local controller |
| experiment validity | Doc 03 protocol + run manifest |

The dashboard is never the authority for physical truth.

---

## 4.8 Edge-controller decision

The purchased board contains two ESP32-S3R2 MCUs.

P0 decision:

> **Use one MCU as the primary runtime controller.**

Current integration convention:

> **right-hand MCU preferred as the primary controller**, subject to actual board labeling/pinout verification.

The second MCU is:

```text
reserved / spare / optional future role
```

It is not used to manufacture artificial distributed-system complexity.

A second MCU role is opened only when a named requirement cannot be satisfied more simply.

---

## 4.9 Communication baseline

Device/backend communication family:

```text
Wi-Fi
→ TCP/IP
→ MQTT
→ TLS-capable deployment
```

MQTT is retained because the OASIS standard defines it as a lightweight client/server publish-subscribe transport suited to M2M/IoT environments.

Canonical topic families are expected to include:

```text
coldguard/{deviceId}/telemetry
coldguard/{deviceId}/event
coldguard/{deviceId}/state
coldguard/{deviceId}/command
coldguard/{deviceId}/command_ack
```

Exact versioning, QoS and retain semantics belong to Doc 02.

---

## 4.10 Backend decomposition

P0 should remain deployable as a small number of understandable components.

Recommended logical decomposition:

```text
MQTT Broker
    ↓
Backend Application
    ├─ ingestion
    ├─ validation
    ├─ state/twin
    ├─ event/audit
    ├─ command lifecycle
    └─ API/realtime
    ↓
PostgreSQL / TimescaleDB
    ↓
Feature / AI inference
    ↓
Policy
```

This does **not** require each logical box to become an independent microservice.

A reasonable P0 deployment can be:

- one broker container;
- one backend application;
- one PostgreSQL/TimescaleDB container;
- one AI process/service when needed;
- one minimal frontend.

No architecture value is created by splitting five tiny services merely to increase component count.

---

## 4.11 Persistence baseline

ColdGuard needs both:

```text
time-series samples
+
relational experiment/audit state
```

A PostgreSQL-family baseline with optional TimescaleDB hypertable support fits both needs.

Reasons:

- standard SQL;
- transactional command/event metadata;
- run/experiment relations;
- time-indexed telemetry;
- dataset is small enough to keep raw data for the entire project.

The project does not need:

- distributed SQL;
- NoSQL sharding;
- Kafka log storage;

for scale.

---

## 4.12 Twin baseline

Minimum conceptual state:

```text
DeviceTwin
├─ reported
│  ├─ sensors
│  ├─ electrical
│  ├─ applied cooling state
│  ├─ mode
│  ├─ firmware
│  └─ last-seen / sequence
│
├─ desired
│  ├─ requested cooling state
│  ├─ command id
│  └─ validity window
│
└─ derived
   ├─ Tmean/Tmin/Tmax
   ├─ gradient
   ├─ slope/recovery
   ├─ data quality
   ├─ risk
   └─ cooling-health interpretation
```

Derived state must preserve provenance.

Example:

```text
risk = 0.73
```

is incomplete without:

```text
model_version
feature_version
input_time_window
inference_time
```

---

# 5. Data and provenance baseline

## 5.1 Minimum raw telemetry concepts

Exact schema is a Doc 02 concern, but P0 must preserve at least:

```text
identity
- device_id
- boot_id
- sequence
- timestamp

experiment
- run_id
- scenario_id
- controller_id
- hardware_config_id

thermal
- t1
- t2
- t3
- t_air
- rh
- door_state

electrical
- cooling_voltage
- cooling_current
- cooling_power
- cooling_energy_counter

control
- applied_cooling_state
- applied_duty if PWM used

quality
- sensor_quality
- communication_quality
- device_mode

provenance
- firmware_version
- calibration_id
- schema_version
```

---

## 5.2 Raw data is immutable evidence

The project stores:

```text
raw observed record
```

before feature engineering changes meaning.

A later preprocessing bug must not require rerunning the physical experiment if the raw record is valid.

Recommended layers:

```text
L0 raw
L1 validated/normalized
L2 feature windows
L3 model/evaluation datasets
```

No L2/L3 artifact may replace L0.

---

## 5.3 Independent runs, not rows, are the experimental unit

At 1 Hz, one 30-minute run produces:

\[
1800\text{ rows}
\]

Those are temporally dependent observations from one trajectory.

They are not:

```text
1800 independent experiments
```

Therefore train/validation/test grouping and statistical comparison must occur by:

- `run_id`;
- paired run/block;
- day/configuration where appropriate;

before window generation can leak information across splits.

---

## 5.4 Version every state-changing artifact

At minimum:

```text
hardware_config_id
firmware_version
schema_version
calibration_id
feature_version
model_version
policy_version
backend_version / git commit
```

An experiment without sufficient provenance is not report-grade evidence.

---

# 6. Predictive intelligence baseline

## 6.1 Level 0 — deterministic baselines

Mandatory:

```text
threshold
threshold + hysteresis
persistence/debounce if required
```

A predictive model is not evaluated in isolation.

It is evaluated against a controller a real embedded device could execute locally.

---

## 6.2 Level 1 — XGBoost core model

XGBoost remains the core predictive ML baseline because ColdGuard's data are expected to be:

- tabular;
- engineered from time windows;
- relatively small in number of independent runs;
- heterogeneous across thermal, event and electrical features.

Candidate feature families:

```text
instantaneous
- T1 T2 T3
- Tmean Tmin Tmax
- Tstd
- gradient
- Tair
- RH
- door
- branch V/I/P
- applied cooling state

temporal
- slope
- rolling mean
- rolling std
- min/max over past window
- time since door-open
- door-open duration/count
- time since cooling transition
- recovery slope
- cumulative thermal exposure
```

All predictive features must be **past-only** relative to inference time.

---

## 6.3 Prediction target

Core target family:

> **Will the thermal state cross the configured critical criterion within horizon H?**

`H` is **not frozen before plant characterization**.

Candidate horizons may be explored after H0–H7 hardware characterization, for example:

```text
30 s
60 s
120 s
300 s
```

if the 6 L chamber proves dynamically fast.

Longer horizons remain possible if measured plant time constants justify them.

---

## 6.4 Score versus probability

A raw classifier output is called:

```text
risk_score
```

until probability calibration is demonstrated.

Only after calibration evidence may UI/report use language such as:

```text
P(critical within H) = ...
```

This prevents false precision.

---

## 6.5 Why deep learning is not core

A more complex sequence model is considered only if:

1. grouped XGBoost/baselines reveal a real limitation;
2. sufficient independent runs exist;
3. leakage controls remain valid;
4. added performance is measured against added complexity.

Model novelty is not a project requirement.

---

# 7. Closed-loop control baseline

## 7.1 Controller A — reactive

Concept:

```text
if temperature/state exceeds upper boundary:
    cooling ON

if state returns below lower boundary:
    cooling OFF
```

with:

- hysteresis;
- persistence/dwell if needed;
- safety limits.

This is both:

- scientific baseline;
- SAFE_LOCAL foundation.

---

## 7.2 Controller B — predictive

Concept:

```text
valid fresh state
       │
       ▼
predict impending critical state
       │
       ▼
risk/policy boundary crossed?
       │
       ▼
safety gate
       │
       ▼
cooling earlier than reactive threshold
```

Controller B is accepted only if it respects the same physical safety envelope as Controller A.

---

## 7.3 Core actuation mode

For the cleanest P0 A/B claim, the initial controller comparison should avoid unnecessary control degrees of freedom.

Preferred core interpretation:

```text
Controller A and B use the same allowed cooling action.
Primary difference = WHEN the action starts.
```

This reduces confounding.

PWM is available at the hardware level and remains an engineering capability.

Fine-grained multi-duty energy optimization is conditional until:

- IBT-2 behavior is characterized;
- PZEM under PWM is characterized;
- core A/B evidence exists.

---

## 7.4 Actionable intervention window

Define:

```text
Tcritical   = time ordinary critical criterion becomes true
Twarning    = predictive warning time
Tresponse   = physical response time after command
Tlatency    = sensing + communication + inference + policy + command latency
```

A simplified actionable margin:

\[
AIW=T_{critical}-T_{warning}-T_{response}-T_{latency}
\]

A prediction that is statistically early but physically too late is not useful control.

---

## 7.5 Cooling-health reasoning

P0 diagnosis is conservative.

### Verified healthy response candidate

```text
command ON
+
branch current/power present
+
temperature responds in expected direction
```

### Electrical/actuation-response problem candidate

```text
command ON
+
branch current ≈ 0 / outside validated response
```

### Thermal-effectiveness degradation candidate

```text
command ON
+
electrical response within healthy envelope
+
thermal recovery materially worse than baseline
```

ColdGuard must not jump from the last case to:

```text
fan broken
TEC broken
thermal paste failed
```

unless additional evidence proves that specific root cause.

---

# 8. Resilience and cybersecurity baseline

## 8.1 Network/backend failure is an expected state

ColdGuard must not require permanent cloud connectivity for minimum physical protection.

When backend/broker is unavailable:

```text
online predictive mode
        ↓
connectivity lost
        ↓
SAFE_LOCAL
        ↓
local threshold/hysteresis protection
        ↓
reconnect
        ↓
state resynchronization
```

---

## 8.2 SAFE_LOCAL is intentionally simpler than AI mode

SAFE_LOCAL does not attempt to replicate:

- XGBoost;
- full diagnosis;
- Digital Twin;
- experiment analytics.

It protects the minimum physical thermal boundary.

Simplicity is a resilience feature.

---

## 8.3 Command safety baseline

A remote command must have enough information to reject:

- malformed command;
- stale command;
- duplicate/replayed command;
- command for wrong device;
- command outside allowed control range;
- command received while state is invalid for predictive action.

Expected concepts include:

```text
command_id
issued_at
expires_at / ttl
desired action
policy/reason
```

Exact contract belongs to Doc 02.

---

## 8.4 Cybersecurity scope

NIST IR 8259 Rev. 1 (April 2026) frames IoT cybersecurity as product-level risk management rather than a last-minute add-on.

ColdGuard P0 therefore includes a practical baseline:

```text
device identity
broker/device credentials
MQTT over TLS where deployed
topic ACL
backend authorization/RBAC where relevant
command schema/range validation
freshness / replay resistance
software/config version awareness
security-relevant audit
```

Conditional hardening:

- ESP32-S3 Secure Boot v2;
- flash encryption;
- signed update pipeline.

Hardening is valuable but must not delay the core physical research loop unless required by the course rubric.

---

# 9. Experiment and evidence baseline

Detailed methodology belongs to Doc 03.

Doc 00 freezes only what the project must prove.

## 9.1 Core scenarios

### S1 — Normal baseline

Purpose:

- characterize healthy thermal/electrical response;
- establish variance;
- establish cooling envelope.

### S2 — Door disturbance

Controlled door-open event.

Observe:

- MC-38 event;
- temperature slope;
- gradient;
- predictive lead time;
- recovery.

### S3 — Cooling-effectiveness degradation

Only if a **safe, repeatable and non-destructive** degradation method is available.

Goal:

```text
electrical response still present
+
thermal response worse than baseline
```

### S4 — Power/actuator response fault

Create a controlled condition:

```text
command requested
but actuator intentionally not executed
```

Do not create faults by short circuit.

### S5 — Connectivity loss

Disconnect backend/broker path.

Prove:

- SAFE_LOCAL;
- state remains bounded according to fallback policy;
- reconnect/resync.

---

## 9.2 Primary outcomes

### Early Warning Lead Time

\[
EWT=T_{\text{reactive warning}}-T_{\text{predictive warning}}
\]

Positive value means predictive warning occurs earlier.

### Recovery time

\[
T_{rec}=t_{\text{return to target band}}-t_{\text{disturbance/intervention reference}}
\]

Exact reference point is frozen in Doc 03.

### Thermal exposure

A candidate engineering metric:

\[
E_T=\sum_i \max(0,T_i-T_{limit})\Delta t
\]

The exact representative temperature and boundary must be frozen before final experiments.

---

## 9.3 Supporting outcomes

- peak temperature;
- time outside target envelope;
- thermal gradient;
- recovery slope;
- warning false positives;
- missed events;
- PR-AUC;
- Brier/log loss if calibrated probability is claimed;
- cooling-branch Wh/run;
- command→ACK latency;
- command→electrical-response latency;
- command→thermal-response latency;
- reconnect/resynchronization time.

---

## 9.4 Mandatory ablation families

| Ablation | Question |
|---|---|
| **A1 — 1 temperature vs 3** | Does multi-point sensing add value? |
| **A2 — thermal vs thermal + door** | Does disturbance context add value? |
| **A3 — thermal vs thermal + electrical telemetry** | Does PZEM actuator observability add value? |
| **A4 — threshold/hysteresis vs XGBoost** | Does predictive intelligence add value? |
| **A5 — reactive vs predictive control** | Does earlier intervention improve physical outcome? |
| **A6 — online vs backend/network loss** | Does resilience design preserve minimum protection? |
| **A7 — energy-aware control** | Conditional only after core gates |

---

## 9.5 Statistical discipline

The project must report:

- number of independent runs;
- paired/matched design where used;
- distribution, not only mean;
- confidence intervals for primary effects;
- effect size;
- invalid/excluded-run rule defined before final analysis;
- raw values alongside percentages;
- negative result if hypothesis is not supported.

Rows generated at 1 Hz are not used to inflate `n`.

---

## 9.6 Project success criterion

The project is successful when the team can demonstrate, with reproducible evidence, that:

1. the exact purchased testbed operates safely and repeatably;
2. multi-sensor state can be reconstructed with traceable measurement quality;
3. the system distinguishes command intent from electrical and thermal response;
4. predictive evaluation is leakage-safe and compared to deterministic baselines;
5. at least some held-out events provide a positive actionable warning window;
6. predictive control executes through a safety-bounded policy path;
7. closed-loop response is physically verified;
8. at least one paired physical outcome improves relative to reactive control **or** a valid experiment shows why it does not;
9. local protection remains available during backend/network loss;
10. every final claim is backed by raw evidence and versioned configuration.

The project does **not** require all secondary metrics to improve.

---

# 10. Architecture and scope decisions

## ADR-LEVEL DECISION 1 — One TEC is enough for the research question

The project does not need two independently controlled TEC branches to prove:

- early detection;
- intervention timing;
- response verification;
- resilience.

One branch reduces:

- wiring risk;
- calibration burden;
- actuator imbalance;
- thermal asymmetry;
- failure modes unrelated to the research question.

This improves experimental interpretability.

---

## ADR-LEVEL DECISION 2 — Three temperature probes remain core

Reducing to one sensor would simplify hardware but would remove the project's direct spatial-observability question.

Three sensors are already purchased and provide high research value for low additional integration complexity.

---

## ADR-LEVEL DECISION 3 — PZEM is not “extra telemetry”; it closes the actuation-observability gap

Without electrical telemetry:

```text
command accepted
```

can be confused with:

```text
physical load energized
```

PZEM adds an independent evidence layer.

---

## ADR-LEVEL DECISION 4 — One primary ESP32

The second ESP32 on the purchased board does not create an obligation to split firmware.

A single controller minimizes synchronization complexity.

---

## ADR-LEVEL DECISION 5 — Backend architecture remains intentionally small

ColdGuard's dataset and device count do not justify distributed backend infrastructure.

The difficult problems are:

- physical correctness;
- experiment design;
- state semantics;
- safe actuation;

not scale.

---

## ADR-LEVEL DECISION 6 — XGBoost before deep sequence models

Independent run count is expected to be limited relative to row count.

A strong tabular baseline plus causal temporal features gives higher project ROI than prematurely adding deep learning.

---

## ADR-LEVEL DECISION 7 — Reactive control is mandatory

Reactive threshold/hysteresis is simultaneously:

- baseline;
- fallback;
- sanity check;
- failure-safe behavior.

It is not optional.

---

## ADR-LEVEL DECISION 8 — Energy optimization is conditional

Recent refrigeration research demonstrates that predictive/advanced control can improve energy performance in large real systems.

ColdGuard does not need to reproduce commercial chiller savings to be successful.

The primary contribution is verified predictive intervention.

Energy becomes a secondary trade-off after the core loop works.

---

# 11. Failure model

ColdGuard explicitly assumes the following can occur:

## Physical

- sensor bias;
- one sensor missing;
- thermal gradient unexpectedly large;
- poor hot-side rejection;
- condensation risk;
- loose/poor thermal contact;
- TEC branch current different from seller expectation;
- IBT-2 module behavior different from generic online module descriptions.

## Electrical

- wrong polarity during integration if process control fails;
- blown fuse;
- low/no branch current;
- PSU droop;
- hot connector/terminal;
- PZEM communication failure;
- wrong PZEM shunt profile.

## Embedded

- ESP reset;
- boot;
- watchdog/crash;
- stale state after reconnect;
- sensor read timeout;
- Modbus timeout.

## Network

- Wi-Fi disconnect;
- broker unavailable;
- backend unavailable;
- duplicate MQTT delivery depending on QoS/session behavior;
- delayed/stale command.

## AI

- model unavailable;
- uncalibrated score;
- prediction based on invalid/stale sensor state;
- distribution shift between experiments.

## Experimental

- initial condition outside band;
- inconsistent door disturbance;
- changed sensor position;
- hardware revision mixed into one dataset;
- run logging gap;
- temporal leakage;
- model selected using held-out test results.

The architecture must convert failures into:

```text
safe state
or
explicit degraded state
or
visible invalid experiment
```

rather than silent success.

---

# 12. Safety boundary

## 12.1 Hardware invariants at project level

Detailed invariants belong to Doc 01.

Project-level non-negotiables:

```text
cooling branch fused
power wiring not carried by Dupont/jumper
driver OFF on boot/reset until intentionally enabled
fan available whenever TEC can run
electronics kept away from condensation path
no deliberate short-circuit fault injection
PCT218 not used as primary TEC current path
XL4015 not used to power TEC
```

---

## 12.2 AC mains boundary

The project documentation covers the **DC prototype**.

The exposed AC side of a high-power PSU is not an experiment target.

Use a complete/shielded PSU installation and appropriate competent supervision for mains-side work.

No research value justifies unsafe mains experimentation.

---

# 13. Team decomposition

Detailed ownership belongs to Doc 04.

High-level split:

## Member A — Embedded & Thermal Systems

Primary domain:

- exact hardware testbed;
- ESP32;
- sensors;
- PZEM/RS-485;
- IBT-2;
- power wiring;
- TEC/V1;
- physical calibration;
- plant characterization;
- repeatability.

North star:

> produce a safe, characterized physical plant whose data can be trusted.

---

## Member B — AI & Experimental Data

Primary domain:

- data-quality pipeline;
- experimental datasets;
- feature engineering;
- threshold/hysteresis benchmark;
- XGBoost;
- calibration;
- grouped evaluation;
- ablation;
- statistics.

North star:

> prove predictive usefulness without leakage or inflated sample size.

---

## Member C — IoT Backend & Digital Twin

Primary domain:

- MQTT;
- ingestion;
- storage;
- run metadata;
- twin state;
- event/audit;
- API/realtime;
- inference integration;
- observability;
- deployment reproducibility.

North star:

> make every physical sample, prediction and command traceable end to end.

---

## Member D — Control, Security & Resilience

Primary domain:

- policy;
- reactive controller;
- predictive controller;
- command safety;
- cooling-health reasoning;
- SAFE_LOCAL;
- stale/replay protection;
- TLS/ACL/authz baseline;
- outage/recovery experiments.

North star:

> no prediction directly becomes an unsafe physical action.

---

# 14. Documentation hierarchy

The project uses a strict normative hierarchy:

```text
00 Project Scope / Architecture
        ↓
01 Physical + Measurement Correctness
        ↓
02 AIoT Closed-Loop Engineering
        ↓
03 Verification / Experiments / Evidence
        ↓
04 Team Execution
        ↓
05A / 05B / 05C / 05D Individual Playbooks
```

Interpretation:

```text
05 cannot redefine 04 gate
04 cannot weaken 03 evidence
03 cannot change 02 semantics
02 cannot violate 01 physical/correctness rule
01 cannot silently change 00 scope/BOM
```

If documents disagree, the higher normative document wins until reviewed.

---

# 15. Repository spine implied by the architecture

This is an architectural decomposition, not a mandatory final folder naming scheme.

A reasonable repository should make these responsibilities visible:

```text
coldguard/
├─ docs/
│  ├─ 00-project-scope-architecture.md
│  ├─ 01-physical-measurement-correctness-contract.md
│  ├─ 02-aiot-closed-loop-engineering.md
│  ├─ 03-verification-experiments-demo.md
│  ├─ 04-team-execution-plan.md
│  ├─ 05A-member-a-embedded-thermal.md
│  ├─ 05B-member-b-ai-experimental-data.md
│  ├─ 05C-member-c-iot-backend-digital-twin.md
│  └─ 05D-member-d-control-security-resilience.md
│
├─ firmware/
│  └─ edge-controller/
│
├─ backend/
│  ├─ ingestion/
│  ├─ state/
│  ├─ command/
│  └─ api/
│
├─ ml/
│  ├─ data/
│  ├─ features/
│  ├─ training/
│  ├─ evaluation/
│  └─ inference/
│
├─ frontend/
│
├─ infra/
│  ├─ broker/
│  ├─ database/
│  └─ compose/
│
├─ experiments/
│  ├─ manifests/
│  ├─ scenarios/
│  └─ analysis/
│
├─ tests/
│
├─ scripts/
│
└─ evidence/
```

Important architectural rule:

> physical experiment data/evidence is not hidden inside notebooks or personal folders.

---

# 16. Project phases

Doc 04 freezes exact week-by-week scheduling.

Project-level phase intent:

| Phase | Weeks | Primary question |
|---|---:|---|
| **P0 — Freeze & Physical Foundation** | 1–4 | Is the exact purchased hardware safe, compatible and measurable? |
| **P1 — Stable IoT Baseline** | 5–8 | Can the device collect, transmit, store and apply safe reactive commands reproducibly? |
| **P2 — Experimental Data & Diagnosis** | 9–12 | Can controlled disturbances generate trustworthy independent runs and healthy/fault envelopes? |
| **P3 — Predictive Intelligence** | 13–16 | Does prediction add held-out lead time and can it be integrated without bypassing safety? |
| **P4 — Closed Loop & A/B Evidence** | 17–20 | Does predictive intervention improve a physical outcome under matched disturbances? |
| **P5 — Robustness, Statistics & Defense** | 21–24 | Can another reviewer reproduce, audit and defend all final claims? |

---

# 17. Core release gates

## Gate A — Physical feasibility

Required:

- exact P0 hardware assembled;
- no abnormal hot connector/wire/driver behavior in allowed test range;
- stable sensor identities;
- PZEM communication valid;
- branch current/power plausible against reference checks;
- thermal pull-down/recovery measurable;
- repeated disturbance produces analyzable response.

Fail:

> do not collect “AI dataset”.

---

## Gate B — Data readiness

Required:

- synchronized run metadata;
- raw data immutable;
- quality flags defined;
- no untracked hardware configuration changes;
- repeated runs usable;
- train/validation/test grouping policy frozen.

---

## Gate C — Prediction readiness

Required:

- deterministic baselines implemented;
- grouped XGBoost benchmark;
- leakage audit;
- warning semantics defined;
- no probability wording without calibration evidence.

---

## Gate D — Control readiness

Required:

- Controller A stable;
- safety gate;
- command freshness/idempotency behavior;
- ACK;
- electrical verification;
- thermal verification;
- SAFE_LOCAL.

Only then enable Controller B physical actuation.

---

## Gate E — Evaluation readiness

Required:

- paired A/B protocol;
- valid-run rules;
- primary outcomes frozen;
- statistical plan;
- evidence automation sufficient for final campaign.

---

## Gate F — Optional scope

Only after A–E are green:

- energy-aware PWM optimization;
- deep sequence model;
- optional extra sensor/fan/proxy hardware;
- advanced security hardening;
- richer product features.

---

# 18. Risk register

| Risk | Probability | Impact | Detection | Architectural mitigation |
|---|---|---|---|---|
| Hot-side V1 rejects insufficient heat | High | Critical | hot side rises, cooling collapses | characterize before AI; bound duty/runtime |
| Purchased TEC differs from generic 12715 assumptions | High | High | measured I/P/response mismatch | SKU-specific commissioning; no generic rating freeze |
| IBT-2 module differs from online schematic/rating | Medium | High | logic failure/module heating | low-power bring-up; module characterization |
| PZEM serial revision differs | Medium | Medium | no Modbus response | configurable 8N1/8N2; verify shipped unit |
| PZEM averaging under PWM misleading | Medium | High for energy claims | nonphysical power relation | characterize; keep energy optimization conditional |
| Board GPIO routing conflicts | Medium | High | peripheral failure | verify actual board before pin freeze |
| Condensation | Medium | High | visible moisture / sensor anomalies | physical separation/sealing/limits |
| Sensor positional drift | Medium | High academically | run variance increases | fixed mounting and position IDs |
| Temporal leakage | High initially | Critical academically | suspicious model scores | group split before windows |
| Too few independent runs | Medium | High | wide CI / unstable result | pilot variance → targeted repetitions |
| Prediction is early but not actionable | Medium | High | AIW ≤ 0 | include response-time physics in evaluation |
| Scope creep | High | High | core gates slip | Gate F |
| Network loss | Expected test case | Medium | broker disconnect | SAFE_LOCAL |
| AI unavailable | Expected test case | Medium | inference error | fallback to reactive policy |
| Energy optimization distracts core | Medium | Medium | experiment delay | secondary/conditional only |

---

# 19. Claim discipline

## Allowed project-level claims if evidence supports them

- ColdGuard is a low-cost AIoT cyber-physical testbed.
- It observes multiple thermal points and cooling-branch electrical behavior.
- It compares reactive and predictive intervention.
- It verifies electrical and thermal response after actuation.
- It can quantify early-warning lead time.
- It can quantify thermal exposure/recovery under controlled experiments.
- It maintains deterministic local fallback under specified cloud/network-loss tests.
- Its findings are valid for the tested prototype/configuration.

## Claims requiring stronger evidence

Only claim if specifically demonstrated:

- prediction probability;
- cooling degradation class;
- energy reduction;
- robustness across different chamber geometry;
- generalization to other hardware.

## Prohibited overclaims

Do not claim:

- commercial reefer equivalence;
- full cold-chain Digital Twin;
- food safety certification;
- universal freshness/shelf life;
- guaranteed energy saving in real warehouses;
- fault root cause the sensors cannot distinguish;
- “43 A IBT-2 continuous” from chip current-limit wording;
- “TEC1-12715 = exactly 180 W” without measurement;
- “AI is better” from random-row cross-validation.

---

# 20. Defense narrative

## 20.1 The 30-second version

> ColdGuard uses three spatial temperature sensors, environmental and door context, and direct electrical observation of its cooling branch to estimate the dynamic state of a 6 L cold-chain testbed. Instead of waiting for a reactive temperature threshold, the system evaluates whether a critical state is approaching, routes that prediction through a safety policy, actuates one Peltier cooling branch, then verifies both electrical and thermal response. We compare the predictive controller against a deterministic threshold/hysteresis baseline using repeatable physical A/B experiments, while the ESP32 retains a local fallback when the network/backend is unavailable.

---

## 20.2 Why three temperatures?

> One temperature is a point sample. Three fixed probes let the system observe spatial gradient and whether a door disturbance or recovery is distributed uniformly. The project proves whether those extra observations are actually useful through ablation rather than assuming they are.

---

## 20.3 Why PZEM?

> An MQTT ACK proves only that software handled a command. PZEM provides independent evidence that the cooling branch drew voltage/current/power. Temperature then provides a second physical layer showing whether that electrical action produced a thermal effect.

---

## 20.4 Why not deep learning first?

> The number of independent physical trajectories is much smaller than the number of telemetry rows. XGBoost with past-only engineered features is a high-ROI baseline. More complex sequence models are justified only after the simple model exposes a measurable limitation.

---

## 20.5 Why a 6 L chamber is acceptable

> It is a miniature physical testbed, not a warehouse emulator. The small thermal volume makes controlled disturbances, recovery tests and repetitions practical. Claims are deliberately limited to the testbed and methodology.

---

# 21. Final project claim

> **ColdGuard is a low-cost AIoT cyber-physical testbed built on the team's exact frozen hardware configuration. It reconstructs dynamic thermal state from multi-point sensing and disturbance context, observes cooling-branch electrical behavior, predicts impending thermal risk, routes any intervention through safety-bounded control, and verifies the resulting electrical and thermal response. Its central contribution is evaluated against deterministic reactive control through repeatable physical experiments, leakage-safe predictive evaluation, ablation and uncertainty-aware statistical reporting.**

## One-line defense

> **ColdGuard không cố đo “nông sản đã hỏng bao nhiêu”; nó chứng minh liệu một hệ thống IoT giá thấp có thể nhận ra thermal degradation sớm, can thiệp an toàn trước reactive threshold và đo được rằng can thiệp đó thực sự tạo ra physical outcome tốt hơn hay không.**

---

# Appendix A — Frozen subsystem map

| Subsystem | Exact P0 hardware | Architectural purpose |
|---|---|---|
| Multi-point thermal sensing | DS18B20 waterproof 1 m ×3 | spatial temperature state |
| Environmental context | BME280 3.3 V ×1 | T/RH context |
| Disturbance context | MC-38 ×1 | door event |
| Electrical observation | PZEM-017 ×1 + 50 A/75 mV shunt ×1 | cooling branch V/I/P/Wh |
| RS-485 interface | MAX3485 3.3 V ×1 | ESP32 UART ↔ PZEM RS-485 |
| Edge controller | Dual ESP32-S3R2 + W25Q32 + CH343G board ×1 | sensing, local logic, network, command |
| Power control | BTS7960/IBT-2 ×1 | TEC branch switching/control |
| Cooling actuator | exact purchased TEC1-12715 SKU ×1 | heat pumping |
| Thermal assembly | V1 12 V ×1 | cold/hot-side transfer + fan |
| Testbed | HS2 6 L ×1 | controlled thermal environment |
| Main power | PSU 12 V/33 A ×1 | DC supply |
| Logic conversion | XL4015 ×1 | 12 V → 5 V logic |
| Protection | ATO 4-way + fuse set | branch protection |
| Distribution | TB4504 45 A 4P | high-current distribution |
| Auxiliary connection | PCT218 8-port | low-current connection/distribution |
| Wiring | 2×2.5 mm² + 2×0.75 mm² + jumpers | frozen conductor set |

---

# Appendix B — Hardware facts versus commissioning facts

## Frozen before commissioning

```text
BOM identity
quantities
chamber = HS2 6 L
PSU = 12 V / 33 A
shunt = 50 A / 75 mV
primary sensing = 3×DS18B20 + BME280 + MC-38
electrical observation = PZEM-017
RS485 interface = MAX3485 3.3 V
driver = IBT-2/BTS7960
actuator = one purchased TEC1-12715 SKU
thermal assembly = V1 12 V
```

## Must be measured after assembly

```text
actual TEC current at 12 V
actual TEC branch power
selected final 10/15/20 A fuse
IBT-2 logic compatibility with actual board
IBT-2 temperature in operating region
V1 heat-rejection capability
cool-down curve
recovery curve
spatial gradient
run-to-run variability
PZEM behavior under PWM
final GPIO map if board routing forces adjustment
plant response time
appropriate prediction horizon
healthy electrical envelope
healthy thermal-response envelope
```

---

# Appendix C — Core state vector candidate

A project-level state vector may conceptually contain:

\[
x_t=
[
T_1,T_2,T_3,
T_{air},RH,
Door,
V_{cool},I_{cool},P_{cool},
u_{cool},
G_T,
\dot T,
R,
E_T,
Q
]
\]

where:

- \(u_{cool}\): applied cooling action;
- \(G_T\): spatial thermal gradient;
- \(\dot T\): past-only thermal slope;
- \(R\): recovery-related feature;
- \(E_T\): thermal exposure feature;
- \(Q\): data-quality/degraded-state representation.

The final ML feature vector is narrower and versioned in Doc 02/05B.

---

# Appendix D — Reference sources

The references below are used for architectural validation and 2026 positioning.  
Vendor/community sources do **not** override the team's exact purchased BOM.

## D.1 Hardware / standards

**[R1] Analog Devices — DS18B20: Programmable Resolution 1-Wire Digital Thermometer.**  
Unique 1-Wire, multidrop, 64-bit ROM, ±0.5 °C range specification.  
https://www.analog.com/en/products/ds18b20.html

**[R2] Bosch Sensortec — BME280.**  
3.3 V-compatible supply ranges, I²C/SPI, humidity and response-time technical data.  
https://www.bosch-sensortec.com/en/products/environmental-sensors/humidity-sensors-bme280

**[R3] Espressif — ESP32-S3 Series Datasheet v2.2.**  
ESP32-S3R2 = 2 MB Quad SPI PSRAM; current lifecycle status.  
https://documentation.espressif.com/esp32_s3_datasheet_en.pdf

**[R4] Espressif — ESP32-S3 GPIO / RTC GPIO Programming Guide.**  
GPIO matrix and flash/PSRAM-related GPIO restrictions.  
https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/gpio.html

**[R5] Analog Devices — MAX3485.**  
3.3 V half-duplex RS-485/RS-422 transceiver.  
https://www.analog.com/en/products/max3485.html

**[R6] Infineon — BTS7960 Datasheet Rev. 1.1.**  
Half-bridge chip features, logic-level input, protection, PWM capability and current limitation.  
https://www.infineon.com/dgdl/BTS7960_Datasheet.pdf?fileId=db3a304412b407950112b43945006d5d&folderId=db3a304412b407950112b408e8c90004

**[R7] Peacefair-style PZEM-017 DC RS-485/Modbus manual mirror.**  
PZEM-017 shunt profiles, Modbus registers, resolution and communication-power requirements.  
https://manuals.plus/ae/32913960037

**[R8] Ferrotec — Thermoelectric Reference Guide.**  
Thermoelectric heat-pump and heat-sink fundamentals.  
https://thermal.ferrotec.com/technology/thermoelectric-reference-guide/

**[R9] OASIS — MQTT Version 5.0.**  
Lightweight client/server publish-subscribe messaging standard.  
https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html

**[R10] NIST IR 8259 Rev. 1 (2026).**  
Foundational Cybersecurity Activities for IoT Product Manufacturers.  
https://doi.org/10.6028/NIST.IR.8259r1

**[R11] NIST IR 8259A.**  
IoT Device Cybersecurity Capability Core Baseline.  
https://doi.org/10.6028/NIST.IR.8259A

**[R12] AWS IoT Core — Device Shadow documents.**  
Reference pattern for `desired`, `reported`, versioned device state.  
https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-document.html

## D.2 2025–2026 research / context

**[R13] Vukšić, M. et al. (2026). Early Anomaly Detection in Maritime Refrigerated Containers Using a Hybrid Digital Twin and Deep Learning Framework. Applied Sciences 16(4), 1887.**  
https://doi.org/10.3390/app16041887

**[R14] Ugwu, C. N. et al. (2026). Digital twins for food processing and shelf-life: linking mechanistic models, sensors, and AI to predict quality, safety, and waste through near-real-time decision support. Frontiers in Food Science and Technology.**  
https://doi.org/10.3389/frfst.2026.1813819

**[R15] Sustainable Futures (2026). Development of a generic implementation concept for autonomous IoT-based temperature monitoring in multi-stakeholder food supply networks.**  
https://doi.org/10.1016/j.sftr.2026.101890

**[R16] Lin, X., Shan, K., Wang, S. (2025). Model predictive control of large chiller plants for enhanced energy efficiency utilizing inherent cold storage of cooling systems. Journal of Energy Storage 113, 115697.**  
https://doi.org/10.1016/j.est.2025.115697

**[R17] Liu, X. et al. (2025). An optimization strategy of cold storage temperature control based on energy consumption prediction. Journal of Building Engineering.**  
https://doi.org/10.1016/j.jobe.2025.113471

**[R18] Báo Chính phủ (24/12/2025). Xuất khẩu rau quả năm 2025 đạt kỷ lục 8,5 tỷ USD.**  
https://baochinhphu.vn/rau-qua-xuat-khau-nam-2025-dat-ky-luc-85-ty-usd-cao-nhat-tu-truoc-den-nay-10225122410173414.htm

**[R19] FiinResearch (21/07/2026). Vietnam Cold Chain Market Report 2026 — public summary.**  
https://fiinresearch.vn/Store/ReportDetails?id=230576

## D.3 Community evidence used only as implementation-risk signal

**[R20] Arduino Forum — IBT-2/BTS7960 board variation discussion.**  
Community inspection reports that inexpensive IBT-2 boards may differ from commonly circulated schematics in buffer/resistor details. This is used only to justify commissioning the actual purchased module, not as a primary electrical specification.  
https://forum.arduino.cc/t/bts7960-btn7960n-ibt-2-motor-drive-module/1142926

**[R21] Arduino Forum — PZEM-017 integration discussion.**  
Historical field evidence of revision/serial-format integration pitfalls. Primary semantics remain the PZEM manual and actual shipped unit.  
https://forum.arduino.cc/t/pzem-017-issue/601324

---

# Appendix E — Source authority order for hardware

When sources disagree, use this order:

```text
1. physical marking / documentation shipped with the exact purchased unit
2. manufacturer's official datasheet for the exact IC/SKU
3. team's measured commissioning result
4. reputable technical manual / distributor documentation
5. seller listing
6. community/forum evidence
```

Exception:

> A measured result never authorizes operation outside manufacturer absolute limits for a known exact component.

For modules assembled from multiple ICs:

```text
IC datasheet
≠
module continuous rating
```

For the purchased TEC:

```text
generic TEC1-12715 Internet datasheet
≠
exact SKU characterization
```

This authority rule is mandatory for all downstream ColdGuard documents.
