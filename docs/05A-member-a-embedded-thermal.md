# COLDGUARD — HỆ THỐNG BẢO VỆ CHUỖI LẠNH CHỦ ĐỘNG
## Member A Execution Playbook · Embedded · Electrical · Thermal · Physical Evidence

> **Document:** `docs/05A-member-a-embedded-thermal.md`  
> **Course:** Internet of Things (IoT) — Course Project / Bài tập lớn  
> **Project:** **ColdGuard — Hệ thống bảo vệ chuỗi lạnh chủ động**  
> **Role:** **Member A — Embedded & Thermal Systems**  
> **Planning horizon:** **24 weeks**  
> **Planned focused effort:** **276 hours**  
> **Average:** **11.5 h/week**  
> **Parents:**  
> `00-project-scope-architecture.md`  
> `01-physical-measurement-correctness-contract.md`  
> `02-aiot-closed-loop-engineering.md`  
> `03-verification-experiments-demo.md`  
> `04-team-execution-plan.md`  
> **Sibling playbooks:** `05B`, `05C`, `05D`  
> **Normative role:** chronological execution contract for Member A. This document converts the physical/hardware responsibilities defined by Docs 00–04 into weekly issue packs, quantitative acceptance criteria, evidence artifacts, handoffs and leader-review checkpoints.  
> **Non-authority rule:** this playbook MUST NOT redefine BOM, physical semantics, MQTT contracts, model semantics, statistical rules, safety hierarchy or team gate meaning. If this file conflicts with Docs 00–04, the parent document wins.  
> **Hardware policy:** **HARDWARE FREEZE.** Member A uses the exact purchased 24-item configuration frozen in Docs 00–01. No silent replacement, omission or “temporary better component” is allowed in evidence-grade work.  
> **Primary mission:** transform the purchased hardware into a **safe, versioned, repeatable physical plant** that can produce trustworthy thermal/electrical evidence for Members B/C/D and the final A/B experiment.

> **Member A north star.**  
> **The job is not “make the Peltier cold.” The job is to make every physical measurement and actuation defensible: known hardware, known sensor identity, safe power, measured current, repeatable thermal dynamics, explicit degraded states, reproducible disturbance and evidence that downstream AI/control can trust.**

---

# 0. How to use this playbook

Every week must end with a **reviewable artifact**.

A task is not complete because:

```text
sensor prints values
TEC feels cold
dashboard moves
```

A task is complete only when it has:

```text
implementation
+
measurement
+
acceptance criterion
+
evidence
+
handoff
```

Member A protects the project's earliest critical path:

```text
exact hardware
→ safe commissioning
→ trustworthy sensing
→ electrical observability
→ stable thermal plant
→ repeatable disturbance
→ valid dataset
→ predictive evidence
→ safe closed loop
```

If this chain is weak, no downstream model or backend polish can repair the scientific claim.

---

# 1. Role contract

## 1.1 Member A owns

### Hardware identity

```text
Dual ESP32-S3R2 + W25Q32 + CH343G
DS18B20 waterproof 1 m ×3
BME280 3.3 V
MC-38
PZEM-017
50 A / 75 mV shunt
MAX3485 3.3 V
BTS7960 / IBT-2
exact purchased TEC1-12715 SKU
V1 12 V thermal assembly
HS2 6 L chamber
12 V / 33 A PSU
XL4015
ATO fuse box
10/15/20 A fuse set
5 A fuses
TB4504 45 A 4P
PCT218 8-port
2×2.5 mm² power wire
2×0.75 mm² auxiliary wire
jumpers / headers / 4.7 kΩ / thermal paste
```

### Physical integration

- sensor installation;
- ROM↔position mapping;
- 1-Wire acquisition;
- BME/door acquisition;
- RS-485/PZEM;
- IBT-2 logic/power integration;
- TEC/V1 installation;
- power distribution;
- fuse selection;
- safe default state.

### Plant characterization

- cool-down;
- warm-up;
- response delay;
- recovery;
- spatial gradient;
- current/power envelope;
- OFF-state electrical envelope;
- repeatability;
- physical initial/reset criteria.

### Firmware physical layer

- deterministic acquisition;
- quality flags;
- hardware configuration/version;
- command apply/ACK physical side;
- local safe behavior with D;
- device telemetry source fields with C.

### Physical evidence

- H0–H8 commissioning;
- S1/S2 execution;
- safe S4 physical support;
- final paired A/B physical operation;
- hardware handover.

---

## 1.2 Member A does not own

Member A does not independently redefine:

```text
prediction target
XGBoost threshold
statistical test
MQTT QoS policy
database schema authority
backend RBAC
Controller B policy semantics
```

Those belong to B/C/D and parent docs.

A may review them when they depend on physical truth.

---

# 2. Exact hardware freeze

## 2.1 Purchased BOM

| ID | Purchased item | Frozen specification | Qty |
|---|---|---|---:|
| HW-01 | Board điều khiển | **Dual ESP32-S3R2 + W25Q32 + CH343G** | **1** |
| HW-02 | DS18B20 | **Waterproof, dây 1 m** | **3** |
| HW-03 | BME280 | **I²C, module 3.3 V** | **1** |
| HW-04 | MC-38 | **Reed switch** | **1** |
| HW-05 | PZEM-017 | **RS485 / Modbus** | **1** |
| HW-06 | Shunt | **50 A / 75 mV** | **1** |
| HW-07 | MAX3485 | **Module RS485 3.3 V** | **1** |
| HW-08 | BTS7960 / IBT-2 | **H-Bridge module** | **1** |
| HW-09 | TEC1-12715 | **Đúng SKU / sản phẩm đã chọn** | **1** |
| HW-10 | Bộ tản Peltier V1 | **12 V** | **1** |
| HW-11 | Chamber | **HS2 6 L** | **1** |
| HW-12 | PSU | **12 V / 33 A, khoảng 400 W** | **1** |
| HW-13 | XL4015 | **DC-DC Buck** | **1** |
| HW-14 | Fuse Box | **ATO 4-way** | **1** |
| HW-15 | Fuse TEC | **10 A / 15 A / 20 A** | **1 bộ** |
| HW-16 | Fuse phụ | **5 A** | **≥2** |
| HW-17 | TB4504 | **45 A 4P** | **1** |
| HW-18 | PCT218 | **8 cổng** | **1** |
| HW-19 | Dây công suất | **2×2.5 mm²** | **~2 m** |
| HW-20 | Dây phụ | **2×0.75 mm²** | **~1 m** |
| HW-21 | Jumper | **M-M / M-F / F-F** | **1 bộ** |
| HW-22 | Header | **2.54 mm** | **đủ** |
| HW-23 | Điện trở | **4.7 kΩ** | **≥1** |
| HW-24 | Thermal paste | **Đi kèm V1** | **đủ** |

---

## 2.2 Explicitly obsolete hardware assumptions

Member A must reject old notes mentioning:

```text
ESP32-S3 N16R8 ×2 as two-node design
INA226 ×2
IRLB3813 ×2
TEC ×2
PSU 12 V / 40 A
20 L foam chamber
120 mm fans ×4
dual cooling branches
current_1/current_2
power_1/power_2
```

They do not describe the current testbed.

---

# 3. Technical facts Member A must know

## 3.1 DS18B20

Manufacturer-level facts:

- 1-Wire;
- unique 64-bit ROM;
- multi-drop;
- 9–12 bit resolution;
- ±0.5 °C specified from −10 to +85 °C;
- 12-bit conversion can take up to roughly 750 ms.

Implication:

> 1 Hz with three probes should use one shared conversion phase and read each known ROM afterward, not three sequential 750 ms conversions.

Recommended conceptual cycle:

```text
start conversion for bus
→ wait/non-block until conversion complete
→ read T1 ROM
→ read T2 ROM
→ read T3 ROM
→ validate
→ build one coherent thermal snapshot
```

---

## 3.2 BME280

Manufacturer facts include:

```text
3.3 V-compatible supply
I²C/SPI
RH response ~1 s
RH accuracy tolerance ~±3% under specified conditions
```

Implication:

- 1 Hz is sufficient;
- BME is context;
- do not make it thermal ground truth.

---

## 3.3 MAX3485

Official MAX3485 family:

```text
3.3 V supply
half-duplex RS-485
up to 10 Mbps class
driver/receiver enable
```

PZEM communication is slow relative to this.

The hard problems are:

- direction control;
- wiring;
- PZEM revision;
- timeout.

---

## 3.4 PZEM-017

Current manual families document:

```text
RS-485 / Modbus RTU
50 A external-shunt profile = 0x0001
voltage resolution = 0.01 V
current resolution = 0.01 A
power resolution = 0.1 W
energy resolution = 1 Wh
```

Important:

- manual revisions in circulation differ on stop-bit details;
- confirm the exact shipped unit.

---

## 3.5 BTS7960 / IBT-2

Infineon BTS7960 silicon supports:

- logic-level control;
- current/thermal protection;
- PWM up to ~25 kHz;
- typical current-limitation figure around 43 A under specified conditions.

The purchased IBT-2 module is not the bare chip.

Therefore:

> `43 A` is not a legal continuous-current claim for the module.

Member A must characterize actual behavior.

---

## 3.6 ESP32-S3R2

Espressif's hardware documentation identifies S3R2 with:

```text
2 MB in-package Quad SPI PSRAM
```

The Octal S3R8/S3R8V mapping uses GPIO33–37 for extra data/DQS.

Do not infer exact board pin availability from chip naming alone.

The custom dual board routing remains the final authority.

---

## 3.7 TEC thermodynamics

For a thermoelectric cooler:

\[
P_{in}=VI
\]

and:

\[
Q_h = Q_c + P_{in}
\]

Hot side must reject:

```text
heat pumped from chamber
+
electrical input heat
```

Therefore a cold side that initially cools does not prove the assembly can sustain the operating point.

---

# 4. Core calculations Member A must maintain

## 4.1 PSU nameplate

\[
12V\times33A=396W
\]

This is maximum nameplate capacity.

Not measured consumption.

---

## 4.2 Shunt resistance

\[
R_s=\frac{75mV}{50A}=1.5m\Omega
\]

At 15 A:

\[
V_s=22.5mV
\]

\[
P_s=I^2R=0.3375W
\]

---

## 4.3 Cooling branch power

At measured sample:

\[
P=VI
\]

Never substitute:

```text
TEC name contains 15
→ current = 15 A
```

---

## 4.4 Short-run energy

\[
E_{Wh}\approx\frac{1}{3600}\sum_i P_i\Delta t_i
\]

Use PZEM energy counter as secondary cross-check.

---

## 4.5 Thermal gradient

\[
G_T=T_{max}-T_{min}
\]

Use as a spatial-state proxy.

---

## 4.6 Response delay

Concept:

```text
command applied at t0
electrical response at te
thermal trajectory response at tt
```

\[
T_{electrical}=t_e-t_0
\]

\[
T_{thermal}=t_t-t_0
\]

Final response detection method is frozen in characterization/evidence.

---

# 5. Member A Definition of Done

By end W24, Member A must hand over:

```text
exact hardware configuration record
safe physical wiring
fuse selection rationale
final pin map
sensor ROM map
placement map
calibration/consistency evidence
PZEM configuration proof
IBT-2 default-off proof
TEC polarity / safe operating point
healthy electrical envelope
thermal response windows
repeatability data
S1/S2 physical protocols
H0–H8 evidence
final A/B run operations
physical limitations
hardware recovery/runbook
```

---

# 6. Member A interfaces

## 6.1 A → B

Must provide:

```text
valid/invalid run status
run_id
hardware_config_id
calibration_id
sensor identity / placement
door disturbance timestamps
applied cooling
PZEM V/I/P
quality flags
physical response delay
pairing context
```

---

## 6.2 A → C

Must provide:

```text
real telemetry fixture
field semantics
device boot/seq behavior
firmware version
quality status
command applied state
ACK device-side information
```

---

## 6.3 A → D

Must provide:

```text
OFF electrical envelope
healthy ON current/power range
allowed duty/state
thermal response window
default-off behavior
sensor degraded behavior
physical failure evidence
```

---

## 6.4 Inputs A needs

### From C

- broker endpoint;
- schema fixture;
- command/ACK contract;
- run metadata interface.

### From B

- final experiment scenario requirements;
- feature/ablation needs;
- pair matching variables.

### From D

- Controller A thresholds;
- allowed command range;
- SAFE_LOCAL rules;
- fault-injection constraints.

---

# 7. Recommended firmware boundaries

```text
components/
├─ hardware_config/
├─ one_wire/
├─ temperature/
├─ bme280/
├─ door/
├─ rs485/
├─ pzem017/
├─ cooling_driver/
├─ safety/
├─ telemetry/
├─ command/
├─ quality/
└─ health/
```

Folder names may differ.

Boundary clarity matters.

---

# 8. Evidence conventions

For each week:

```text
evidence/A/Wxx/
```

Recommended artifact names:

```text
README.md
measurements.csv
serial.log
photo-*.jpg
plot-*.png
config.yaml
acceptance.md
```

Every evidence README should include:

```text
date
operator
hardware_config_id
firmware commit
test IDs
setup
result
pass/fail
anomalies
```

---

# 9. Personal risk register

| Risk | Member A response |
|---|---|
| wrong GPIO due custom board | verify before final pin freeze |
| DS18B20 identity swap | ROM mapping |
| RS-485 no response | A/B + power + serial revision checklist |
| wrong PZEM range | readback 50 A profile |
| IBT-2 module inconsistent | conservative commissioning |
| TEC seller spec inaccurate | measure actual current |
| hot-side saturation | characterize before dataset |
| chamber too fast | derive horizon from measured physics |
| condensation | keep electronics outside chamber |
| sensor movement | fixture/photo/config |
| operator disturbance variability | timed protocol |
| hardware change mid-campaign | new hardware_config_id |

---

# 10. Week 01 — Exact BOM audit, board/module identification and physical risk ledger
**Effort budget:** **11 h**  
**Parent:** `04 W01`

## Objective

Prove that the team knows exactly what it physically owns before any high-power integration.

---

## Prerequisites

- Docs 00–04 available;
- all purchased components physically present where possible;
- no powered TEC testing.

---

## A-W01-01 — BOM reconciliation

Physically reconcile HW-01…HW-24.

For every item record:

```text
present?
quantity?
visible marking?
seller/SKU identifier?
physical condition?
unknown?
```

Artifact:

```text
evidence/A/W01/bom-audit.csv
```

---

## A-W01-02 — Photo inventory

Photograph:

- both sides of dual ESP32 board;
- DS18B20 labels/probes;
- BME;
- MC-38;
- PZEM;
- shunt;
- MAX3485;
- IBT-2;
- TEC package/SKU marking;
- V1;
- PSU;
- fuse/distribution components.

Purpose:

> eliminate future ambiguity about which module was characterized.

---

## A-W01-03 — Board pin investigation

Compare:

- silkscreen;
- available schematic/manual if seller provides;
- ESP32-S3R2 chip restrictions.

Do not freeze GPIO yet.

Create:

```text
pin-candidates-v0.md
```

Mark:

```text
known
likely
unknown
must test
```

---

## A-W01-04 — Electrical risk ledger

List at minimum:

- polarity;
- high current;
- fuse;
- PSU terminals;
- shunt placement;
- IBT-2 boot state;
- fan dependency;
- condensation;
- USB/back-power concern;
- RS-485 power domain.

---

## A-W01-05 — Legacy assumption purge

Search old physical notes for:

```text
INA226
IRLB3813
two TEC
20L
40A PSU
```

Flag as obsolete.

Do not delete historical source evidence; stop using it as execution authority.

---

## Deliverables

```text
bom-audit.csv
photo inventory
pin-candidates-v0.md
physical-risk-ledger.md
```

---

## Pass criteria

```text
24-item list reconciled
no unexplained core item substitution
no old architecture carried forward
uncertain module facts explicitly marked unknown
```

---

## Handoff

### To C

- board/device identifier convention;
- candidate firmware device identity.

### To D

- physical risk ledger.

### To leader

- exact hardware audit.

---

## Leader review

Ask:

1. Is the exact TEC SKU photographed?
2. Is the shunt visibly 50 A / 75 mV?
3. Is the MAX3485 module confirmed 3.3 V?
4. Did A invent any module rating?

---

## Contingency

If a purchased core item is missing or visibly wrong:

```text
project configuration review
```

before downstream physical work.

---

# 11. Week 02 — Mechanical assembly, T1/T2/T3 identity and low-risk sensors
**Effort budget:** **12 h**  
**Parent:** `04 W02`

## Objective

Pass H0/H1 without TEC power.

---

## A-W02-01 — Mechanical H0

Install/freeze:

- V1 location;
- TEC mechanical stack;
- chamber penetration;
- hot-side outside;
- sensor fixture;
- MC-38 alignment.

No energized TEC.

---

## A-W02-02 — DS18B20 enumeration

Use official/validated 1-Wire implementation.

Discover exactly three expected ROMs.

Create mapping:

```text
T1 = near door
T2 = center
T3 = far/opposite
```

---

## A-W02-03 — Reboot identity proof

Perform at least:

```text
5 reboot/discovery cycles
```

Assert same ROM→role mapping.

The library enumeration order is irrelevant.

---

## A-W02-04 — Acquisition implementation

Use:

```text
shared conversion
→ read three ROMs
```

rather than three sequential full conversions.

Target logical thermal snapshot:

```text
~1 Hz
```

---

## A-W02-05 — Inter-sensor consistency

Place probes under as similar a stable condition as practical.

Collect:

```text
>=10 min
~1 Hz
```

Compute:

- each probe mean;
- SD;
- pairwise mean differences;
- maximum disagreement.

Do not call it certified calibration unless a traceable reference exists.

---

## A-W02-06 — BME280

Verify:

- I²C address;
- T/RH plausible;
- mounting not immediately heated by ESP32/V1.

---

## A-W02-07 — MC-38

Freeze:

```text
raw input → OPEN/CLOSED
```

Test:

```text
>=20 open/close cycles
```

Check debounce/reliability.

---

## Deliverables

```text
H0 mechanical photos
sensor-rom-map.yaml
sensor-placement.png
H1 serial log
sensor-consistency.csv
door-test.csv
```

---

## Pass criteria

```text
3 unique stable ROMs
no silent remap across reboot
BME responds
door semantic correct
mechanical placement reproducible
```

---

## Handoff

To B:

- position semantics;
- consistency summary.

To C:

- real sensor JSON fixture.

To D:

- physical-quality behavior on missing sensor.

---

## Leader review

Must physically point to:

```text
T1 / T2 / T3
```

and match software IDs.

---

# 12. Week 03 — Logic power, MAX3485/PZEM and IBT-2 logic commissioning
**Effort budget:** **14 h**  
**Parent:** `04 W03`

## Objective

Establish electrical observation without unsafe TEC escalation.

---

## A-W03-01 — XL4015

Before sensitive modules:

- set intended logic output;
- measure with meter;
- record no-load/load value if practical.

Target nominal:

```text
~5 V
```

within safe module requirements.

---

## A-W03-02 — MAX3485

Verify:

```text
module VCC = 3.3 V
```

Map:

```text
DI
RO
DE
/RE
A
B
```

Use ESP-IDF UART/RS-485 mode or explicit direction control.

---

## A-W03-03 — PZEM communication

Verify:

- PZEM communication-side power per shipped module;
- slave address;
- Modbus CRC;
- actual serial framing.

If 8N1 fails:

> review shipped/manual revision before declaring hardware fault.

---

## A-W03-04 — 50 A profile

Read/set current-range register.

Evidence must show:

```text
0x0001
```

or equivalent 50 A configuration.

---

## A-W03-05 — OFF electrical envelope

With TEC physically OFF:

collect:

```text
>=10 min
```

PZEM samples.

Measure:

- voltage;
- current noise/zero;
- power noise/zero;
- Modbus error rate.

---

## A-W03-06 — Shunt installation inspection

Verify:

- correct current path;
- secure terminals;
- no signal-wire use in high-current path;
- physical marking 50 A / 75 mV.

---

## A-W03-07 — IBT-2 logic only

Validate:

- actual module pin labels;
- enable;
- PWM inputs;
- reset/default state.

Do not infer continuous current from `43 A` chip current limit.

---

## Deliverables

```text
logic-power-measurement.md
pzem-register-readback.txt
pzem-off.csv
rs485-wiring.png
ibt2-pin-map.md
```

---

## Pass criteria

```text
MAX3485 powered correctly
PZEM stable enough to poll
50 A range verified
OFF envelope measured
IBT-2 can remain disabled/default OFF
```

---

## Handoff

To C:

- PZEM field semantics;
- error/timeout representation.

To D:

- OFF electrical envelope;
- actuator pin behavior.

---

## Leader review

Ask A to explain:

> why `43 A` is not a module continuous rating.

---

# 13. Week 04 — Fused power branch and conservative first TEC cooling
**Effort budget:** **14 h**  
**Parent:** `04 W04`

## Objective

Pass H4–H6 and produce the first safe measured cooling response.

---

## A-W04-01 — Power path build

Conceptually:

```text
12 V PSU
→ fuse box
→ selected commissioning fuse
→ IBT-2
→ TEC branch
→ shunt / return
```

V1 fan on protected 12 V auxiliary branch.

Logic via XL4015.

---

## A-W04-02 — Wiring class audit

Ensure:

```text
TEC path → 2×2.5 mm²
fan/aux → 2×0.75 mm²
signal → jumper
```

No primary TEC current through PCT218/jumper.

---

## A-W04-03 — Fuse strategy

Start with a conservative legal fuse choice based on measured ramp/current plan.

Do not assume 15 A merely from `12715`.

Final selection remains later characterization-derived.

---

## A-W04-04 — Boot/reset default-off test

With power branch ready:

test at least:

```text
5 cold boots
5 resets
```

Observe PZEM current.

Pass:

```text
no unintended active-branch current
```

beyond measured OFF envelope.

---

## A-W04-05 — First conservative actuation

Use low/conservative control.

Check:

- current;
- branch power;
- intended cold side;
- hot-side behavior;
- V1 fan;
- terminals/wires.

Immediate stop if abnormal.

---

## A-W04-06 — Polarity freeze

Record physical polarity/orientation that makes chamber side cold.

Never infer from wire color later.

---

## A-W04-07 — First response trace

Capture:

```text
command/applied state
V/I/P
T1/T2/T3
time
```

Plot:

```text
electrical response
thermal direction
```

---

## Deliverables

```text
power-topology-v1.png
fuse-commissioning-note.md
boot-default-off.csv
first-tec-trace.csv
first-tec-plot.png
polarity-photo.md
```

---

## Pass criteria

```text
branch fused
fan available
no unsafe connector heating
default OFF
measured branch current
correct cooling polarity
thermal trend changes in expected direction
```

---

## Gate contribution

**G1 physical preliminary**

If any fail:

> W05 real telemetry may continue only for safe sensors; high-power work remains blocked.

---

# 14. Week 05 — Coherent firmware telemetry at ~1 Hz
**Effort budget:** **11 h**  
**Parent:** `04 W05`

## Objective

Turn real hardware into one coherent versioned device snapshot.

---

## A-W05-01 — Firmware task boundaries

Separate:

```text
thermal acquisition
BME
door
PZEM
command state
quality
telemetry
health
```

PZEM timeout must not block local safety forever.

---

## A-W05-02 — Device identity

Implement/freeze:

```text
device_id
boot_id
seq
uptime
firmware_version
hardware_config_id
calibration_id
```

---

## A-W05-03 — 1 Hz timing study

Collect at least:

```text
30 min
```

Measure:

- sample intervals;
- mean;
- P95;
- max gap;
- DS18B20 read failures;
- PZEM read failures.

---

## A-W05-04 — Coherent snapshot

Ensure each published row has:

```text
T1
T2
T3
BME T/RH
door
PZEM V/I/P/Wh
applied cooling
quality
```

with clear missing-state semantics.

---

## A-W05-05 — Quality flags

Implement physical source states such as:

```text
VALID
DEGRADED
INVALID
UNKNOWN
```

Do not replace missing current with previous “fresh” value.

---

## Deliverables

```text
firmware tag/commit
30min-telemetry.csv
timing-jitter.csv
quality-test.md
schema-fixture.json
```

---

## Pass criteria

```text
~1 Hz stable enough for plant dynamics
three thermal identities stable
no duplicate fake sensor values
PZEM timeout bounded
quality explicit
```

---

## Handoff

C receives:

- real schema;
- fixture;
- timing behavior.

B receives:

- data QA sample.

D receives:

- quality-state semantics.

---

# 15. Week 06 — Device command/ACK + physical actuation state
**Effort budget:** **11 h**  
**Parent:** `04 W06`

## Objective

Implement A's half of the command lifecycle without weakening default safety.

---

## A-W06-01 — Command parser

Accept only schema supported by Doc 02.

Check:

```text
device_id
command_id
expiry
action
allowed duty/state
```

---

## A-W06-02 — Idempotency

Same `command_id` twice:

```text
one physical logical application
```

Return canonical result.

---

## A-W06-03 — Expiry

Expired command:

```text
reject
no actuation
```

---

## A-W06-04 — Applied state

Distinguish:

```text
desired command
applied output
```

ACK includes applied state.

---

## A-W06-05 — Physical trace

With C/D:

```text
backend command
→ device accept
→ applied
→ PZEM
→ thermal response
```

---

## A-W06-06 — Reset while command exists

Verify reboot does not automatically resume unsafe stale actuation.

---

## Deliverables

```text
command-parser-tests
duplicate-command-log
expired-command-log
reset-command-log
physical-command-trace
```

---

## Pass criteria

```text
duplicate safe
expired rejected
wrong-device rejected
out-of-range rejected
default OFF preserved
applied state auditable
```

---

# 16. Week 07 — Geometry freeze and physical repeatability study
**Effort budget:** **12 h**  
**Parent:** `04 W07`

## Objective

Make the chamber a reproducible experimental plant rather than an ad-hoc prototype.

---

## A-W07-01 — Geometry freeze

Freeze:

- sensor mounts;
- V1 position;
- cable paths;
- door alignment;
- chamber internal state.

Create configuration photo/drawing.

---

## A-W07-02 — Passive warm-up repetitions

Perform:

```text
>=3 valid pilot runs
```

under similar start conditions.

Measure:

- Tmean trajectory;
- gradient;
- slope.

---

## A-W07-03 — Cooling step repetitions

Perform:

```text
>=3 valid pilot runs
```

same core action.

Measure:

- current/power;
- command→electrical delay;
- thermal response;
- recovery.

---

## A-W07-04 — Repeatability summary

Compute per outcome:

- mean;
- SD;
- CV where meaningful;
- min/max;
- trajectory overlays.

---

## A-W07-05 — Initial/reset criterion candidate

Define state-based candidate:

```text
Tmean band
gradient bound
door CLOSED
known cooling state
valid sensors
```

---

## Deliverables

```text
geometry-v1
warmup-runs
cooling-step-runs
repeatability-report.md
reset-criterion-v0.yaml
```

---

## Pass criteria

Plant variation must be small enough to distinguish deliberate S2 disturbance from random setup drift.

No arbitrary universal threshold is required.

If repeatability is poor:

> fix plant before ML collection.

---

# 17. Week 08 — Gate A physical characterization and SAFE_LOCAL support
**Effort budget:** **12 h**  
**Parent:** `04 W08`

## Objective

Close the first major physical gate.

---

## A-W08-01 — Safe operating envelope

From W4–W7 derive:

```text
allowed action state
healthy current range
healthy power range
OFF current envelope
thermal response window
stop conditions
```

Do not extrapolate outside measured region.

---

## A-W08-02 — Fuse finalization

From measured current/behavior choose among:

```text
10 A
15 A
20 A
```

with rationale.

If no available fuse is defensibly suitable:

> gate fails; do not improvise silently.

---

## A-W08-03 — Hot-side sustainability

Run a sufficiently long cooling test to observe whether:

- response remains stable;
- performance collapses;
- protection triggers;
- terminals/IBT-2 show abnormal behavior.

---

## A-W08-04 — SAFE_LOCAL integration support

With D:

- remove broker/backend;
- verify local Controller A input sensors remain available;
- verify local output behavior.

---

## A-W08-05 — Gate A package

Index all H0–H7 artifacts.

---

## Deliverables

```text
operating-envelope-v1.yaml
fuse-selection.md
thermal-sustainability.csv
Gate-A-report.md
```

---

## Pass criteria

```text
safe physical envelope known
repeatable enough plant
fuse selected
no unresolved high-current anomaly
SAFE_LOCAL physically possible
```

---

# 18. Week 09 — Freeze run protocol and collect S1 baseline
**Effort budget:** **10 h**  
**Parent:** `04 W09`

## Objective

Begin evidence-grade data collection.

---

## A-W09-01 — Run checklist

Before run:

```text
hardware config
sensor identity
PZEM range
initial state
door
storage online
```

After run:

```text
end reason
manual intervention
anomaly
validity candidate
```

---

## A-W09-02 — S1 baseline

Collect baseline runs according to Doc 03 planning.

Initial target:

```text
~4 valid S1 runs
```

adjust based on campaign plan.

---

## A-W09-03 — Physical invalidation logging

Examples:

- sensor moved;
- manual touch;
- fan anomaly;
- missing key telemetry;
- unexpected power event.

Never delete invalid attempt.

---

## A-W09-04 — Healthy response reference

Summarize:

- electrical active range;
- OFF range;
- thermal baseline;
- gradient.

---

## Handoff

B receives valid S1 IDs.

D receives healthy ranges.

C receives run-manifest edge fields.

---

# 19. Week 10 — S2 door-disturbance pilot and fixture
**Effort budget:** **12 h**  
**Parent:** `04 W10`

## Objective

Create the primary reproducible thermal disturbance.

---

## A-W10-01 — Door protocol candidates

Explore a small set of safe durations/operations.

Goal:

- meaningful thermal rise;
- not instantaneous catastrophic crossing;
- enough trajectory for prediction;
- repeatable.

---

## A-W10-02 — Timing method

Use:

- MC-38 transition as machine ground truth;
- operator timer as secondary check.

---

## A-W10-03 — Repeated S2 pilot

Target:

```text
>=4–6 valid pilot disturbances
```

depending run time.

Measure:

- door duration;
- initial T;
- peak;
- gradient;
- time-to-critical candidate;
- recovery.

---

## A-W10-04 — Pair tolerance evidence

Estimate variation of:

- initial Tmean;
- initial gradient;
- response.

Give B evidence to freeze pair-matching tolerance.

---

## A-W10-05 — Horizon support

Give B:

```text
door→critical distribution
controller response distribution
```

Do not select ML horizon yourself.

---

## Deliverables

```text
S2-protocol-v1.md
S2-pilot.csv
door-event-validation.csv
pairing-physics-summary.md
```

---

# 20. Week 11 — Safe actuation-response fault and additional dataset runs
**Effort budget:** **12 h**  
**Parent:** `04 W11`

## Objective

Support diagnosis without unsafe destructive fault injection.

---

## A-W11-01 — S4 method

Preferred:

```text
software/test mode intentionally refuses/blocks actuation
```

while preserving protocol visibility.

Do not:

- short branch;
- bypass fuse;
- damage TEC.

---

## A-W11-02 — S4 evidence

Produce:

```text
command/intention
applied state
PZEM no-active-response
thermal non-response
```

This proves:

```text
command != electrical effect
```

---

## A-W11-03 — Dataset expansion

Collect additional S1/S2 as required by B's run plan.

---

## A-W11-04 — Conditional S3 feasibility

Assess whether a safe repeatable thermal-effectiveness degradation can be created with current frozen hardware.

If not:

```text
NO-GO
```

is acceptable.

Do not invent unsafe fan obstruction.

---

## Deliverables

```text
S4-protocol.md
S4-runs/
S3-go-no-go.md
additional-valid-run-list
```

---

# 21. Week 12 — Drift audit and Month-3 physical/data signoff
**Effort budget:** **10 h**  
**Parent:** `04 W12`

## Objective

Confirm that data collected so far still belong to one defensible physical configuration.

---

## A-W12-01 — Sensor consistency recheck

Repeat W2 consistency method.

Compare offsets/drift.

---

## A-W12-02 — PZEM zero/active check

Compare to W3/W8 envelope.

---

## A-W12-03 — Mechanical audit

Check:

- sensor fixtures;
- V1 mounting;
- terminals;
- fuse;
- cable positions.

---

## A-W12-04 — Hardware config signoff

List all runs under:

```text
CG-HW-001
```

and identify any run that should not be pooled.

---

## A-W12-05 — Gate G3 input

Provide A's signoff:

```text
plant stable enough for predictive development
```

or explicit blockers.

---

# 22. Week 13 — Plant timing and intervention-physics package
**Effort budget:** **8 h**  
**Parent:** `04 W13`

## Objective

Quantify the physical delays B/D need for horizon and AIW.

---

## A-W13-01 — Command→electrical delay

From clean runs calculate distribution:

- median;
- P95;
- max useful observed.

---

## A-W13-02 — Command→thermal response

Define response-detection method with B/D.

Measure across valid step runs.

---

## A-W13-03 — Door→critical time

For pilot trajectories compute distribution under frozen candidate critical definition.

---

## A-W13-04 — Passive/cooling time constants proxy

Fit simple empirical summaries only.

No need for sophisticated physics model.

Candidate:

- exponential response approximation;
- slope-based response time.

Document limitations.

---

## Deliverables

```text
plant-timing-report.md
response-delay.csv
door-critical.csv
```

---

## Handoff

B:

- candidate horizon physical constraints.

D:

- safety margin inputs.

---

# 23. Week 14 — A1 spatial-sensing support and pair-condition refinement
**Effort budget:** **10 h**  
**Parent:** `04 W14`

## Objective

Support the one-sensor-versus-three-sensor ablation without changing physical configuration.

---

## A-W14-01 — Sensor-position QA

Verify no movement since freeze.

---

## A-W14-02 — Logical ablation support

Do not unplug T2/T3 for core A1.

Preferred:

```text
same physical runs
B logically selects one sensor feature set
vs three-sensor set
```

This controls physical conditions.

---

## A-W14-03 — Spatial statistics

Provide:

- gradient distributions;
- max pairwise differences;
- disturbance-specific spatial response.

---

## A-W14-04 — Pairing criterion refinement

With B freeze final A/B initial physical matching tolerances.

---

# 24. Week 15 — A3 electrical-observability support and PWM characterization decision
**Effort budget:** **12 h**  
**Parent:** `04 W15`

## Objective

Quantify what PZEM adds and decide whether PWM/energy work is scientifically safe.

---

## A-W15-01 — Electrical feature integrity

Audit:

- missing PZEM samples;
- sampling cadence;
- ON/OFF separation;
- power consistency.

---

## A-W15-02 — A3 dataset support

Identify runs containing:

```text
command
applied
V/I/P
thermal response
```

for B's electrical ablation.

---

## A-W15-03 — PZEM reference check

If trusted independent meter available:

compare multiple points.

If not:

report:

```text
plausibility/consistency
```

not certified calibration.

---

## A-W15-04 — PWM Go/No-Go

If team intends optional energy-aware duty control:

test limited safe duty points.

Check:

- IBT-2 response;
- PZEM power behavior;
- thermal behavior.

Decision:

```text
GO
NO-GO
```

No shame in NO-GO.

---

## Deliverables

```text
pzem-quality-report.md
A3-run-index.csv
pwm-go-no-go.md
```

---

# 25. Week 16 — Final physical drift/response freeze before predictive control
**Effort budget:** **12 h**  
**Parent:** `04 W16`

## Objective

Confirm the plant used for locked prediction/Controller B has not materially changed.

---

## A-W16-01 — Re-run short characterization

Repeat selected:

- OFF envelope;
- core ON point;
- response delay;
- S2 disturbance.

---

## A-W16-02 — Compare W7/W8 versus W16

Check:

- current/power shift;
- response shift;
- gradient;
- recovery.

---

## A-W16-03 — Final pair tolerances

Sign off with B:

```text
initial state
gradient
reset criterion
disturbance tolerance
```

---

## A-W16-04 — Controller B physical readiness

With D certify:

- allowed action still valid;
- no hardware safety issue;
- H8 reactive verification stable.

---

## Gate contribution

G4 cannot pass if physical response has drifted beyond understood range.

---

# 26. Week 17 — Live plant for closed-loop shadow mode
**Effort budget:** **12 h**  
**Parent:** `04 W17`

## Objective

Provide real live trajectories while Controller A remains physical authority.

---

## A-W17-01 — Shadow S2 runs

Run several S2 trajectories.

B model and D policy produce hypothetical predictive decisions.

A applies only Controller A.

---

## A-W17-02 — Verify no predictive physical path

Check firmware logs/commands:

```text
shadow decision
≠
applied predictive action
```

---

## A-W17-03 — Online/offline physical alignment

Ensure raw live channels match fields expected by B model.

---

## A-W17-04 — Plant anomaly monitoring

Any unexpected physical drift:

- invalidate/flag run;
- do not let B/D tune around hardware malfunction.

---

# 27. Week 18 — Controller B physical enablement
**Effort budget:** **14 h**  
**Parent:** `04 W18`

## Objective

Enable the predictive controller under supervision without changing hardware.

---

## Preconditions

```text
G4 GREEN
model frozen candidate
policy frozen candidate
SAFE_LOCAL works
command verification works
```

---

## A-W18-01 — Pre-run safety audit

Check:

- fuse;
- fan;
- terminals;
- sensors;
- PZEM;
- chamber;
- applied-output default.

---

## A-W18-02 — Controlled predictive dry runs

Begin with small number of S2 runs.

Observe complete chain.

---

## A-W18-03 — Electrical verification

For each intervention:

- current enters expected range;
- OFF state returns correctly.

---

## A-W18-04 — Thermal verification

Check the expected response occurs within characterized window.

---

## A-W18-05 — Abort criteria

Stop if:

- new abnormal current;
- unexpected heating;
- repeated verification failure;
- physical drift.

Do not “keep testing to get a successful run.”

---

## Deliverables

```text
controller-B-dry-run-index
physical-verification-plots
readiness-signoff.md
```

---

# 28. Week 19 — Final paired A/B campaign wave 1
**Effort budget:** **14 h**  
**Parent:** `04 W19`

## Objective

Operate the first half of final matched physical campaign exactly according to Doc 03.

---

## A-W19-01 — Run preparation

Before every run:

```text
hardware config check
initial state
door closed
PZEM valid
storage ready
controller identity
```

---

## A-W19-02 — Physical execution

Follow randomized order supplied by campaign plan.

Do not change:

- door duration;
- sensor placement;
- action magnitude;
- model/policy.

---

## A-W19-03 — Invalid attempt logging

Record all:

- aborted;
- invalid;
- operator error;
- hardware anomaly.

---

## A-W19-04 — Reset

Use state-based reset, not a fixed arbitrary waiting period.

---

## Handoff

B receives validity candidates.

C backs up raw evidence.

D reviews controller trace.

---

# 29. Week 20 — Final paired A/B campaign wave 2
**Effort budget:** **13 h**  
**Parent:** `04 W20`

## Objective

Complete pre-frozen pair target without post-hoc physical changes.

---

## A-W20-01 — Continue exact protocol

No “better” door handling after seeing results.

---

## A-W20-02 — Valid-pair completion

Rerun only according to frozen invalid-pair rule.

---

## A-W20-03 — Campaign close physical audit

After final run:

- inspect hardware;
- recheck sensor identity;
- note damage/drift;
- record final physical config.

---

## A-W20-04 — Freeze physical campaign data

Sign campaign manifest:

```text
hardware unchanged?
yes/no
exceptions
invalid attempts
```

---

## Gate contribution

G5 requires A's physical signoff.

---

# 30. Week 21 — Physical reliability soak + degraded/fault support
**Effort budget:** **10 h**  
**Parent:** `04 W21`

## Objective

Close hardware-side resilience evidence after the primary A/B data are safe.

---

## A-W21-01 — Soak

Run:

```text
2–4 h
```

or an evidence-justified duration.

Monitor:

- sensor read errors;
- PZEM errors;
- ESP stability;
- electrical state;
- thermal behavior.

---

## A-W21-02 — One-sensor degraded case

Safely simulate/disconnect one DS18B20.

Verify:

- explicit degraded state;
- no silent remap.

---

## A-W21-03 — PZEM unavailable

Safely remove/disable communication path.

Verify:

- electrical quality degrades;
- thermal/local control behavior matches policy.

---

## A-W21-04 — Support SAFE_LOCAL final test

With C/D.

---

# 31. Week 22 — Targeted reruns and evidence-gap repair
**Effort budget:** **10 h**  
**Parent:** `04 W22`

## Objective

Repair only evidence problems allowed by Doc 03.

---

## Allowed rerun reasons

- invalid pair under predeclared rule;
- missing required recording;
- known sensor/log failure;
- failed deterministic test due harness defect.

---

## Forbidden

```text
run more because effect is not significant
rerun worst predictive result
adjust door to improve Controller B
```

---

## A-W22-01 — Evidence gap list

With leader/B identify physical gaps.

---

## A-W22-02 — Execute approved reruns

Store original invalid attempt.

---

## A-W22-03 — Physical limitation summary

Write:

- scale;
- single unit;
- TEC/V1 uncertainty;
- sensor limitations;
- ambient effects;
- PZEM limits.

---

# 32. Week 23 — Demo hardening, physical runbook and recovery kit
**Effort budget:** **12 h**  
**Parent:** `04 W23`

## Objective

Make physical demonstration repeatable and recoverable.

---

## A-W23-01 — Physical demo runbook

Sequence:

```text
visual inspection
power-on
sensor check
PZEM check
broker/device check
short legal actuation check
demo scene
safe shutdown
```

---

## A-W23-02 — Recovery kit

Prepare purchased/spare consumables already available:

- fuses from purchased set;
- jumpers;
- headers;
- tools;
- documentation.

Do not introduce unapproved core hardware.

---

## A-W23-03 — Cable/label hardening

Label:

- 12 V;
- 5 V;
- sensor bus;
- RS-485;
- TEC branch;
- shunt.

---

## A-W23-04 — Demo rehearsals

At least three full rehearsals with team.

Measure:

- setup time;
- thermal reset time;
- failure recovery.

---

## A-W23-05 — Evidence package

Index Member A evidence:

```text
commissioning
characterization
A/B physical logs
faults
soak
photos
```

---

# 33. Week 24 — Final freeze, acceptance and Member A handover
**Effort budget:** **8 h**  
**Parent:** `04 W24`

## Objective

No feature development.

Deliver a reproducible physical testbed and evidence package.

---

## A-W24-01 — Final configuration record

Freeze:

```text
hardware_config_id
pin_map
sensor ROMs
sensor positions
fuse
PZEM range
core allowed action
firmware version
```

---

## A-W24-02 — Final HIL smoke

Verify:

```text
T1/T2/T3
BME
door
PZEM
default OFF
short legal ON
current response
return OFF
```

---

## A-W24-03 — Handover run

Another team member follows A's runbook.

A observes but does not silently fix undocumented steps.

---

## A-W24-04 — Final acceptance

Deliver:

```text
hardware configuration
commissioning index
characterization report
plant timing
run protocols
limitations
physical evidence index
```

---

# 34. Weekly effort summary

| Week | Hours | Primary emphasis |
|---:|---:|---|
| 01 | 11 | BOM / risk / board audit |
| 02 | 12 | H0/H1 sensing/mechanical |
| 03 | 14 | PZEM / RS-485 / IBT-2 logic |
| 04 | 14 | fused TEC first cooling |
| 05 | 11 | coherent telemetry |
| 06 | 11 | command/ACK physical side |
| 07 | 12 | geometry/repeatability |
| 08 | 12 | Gate A / SAFE_LOCAL support |
| 09 | 10 | S1 baseline |
| 10 | 12 | S2 pilot |
| 11 | 12 | safe fault + dataset |
| 12 | 10 | drift/signoff |
| 13 | 8 | response-time physics |
| 14 | 10 | A1 support |
| 15 | 12 | A3 / PZEM / PWM Go-No-Go |
| 16 | 12 | physical predictive freeze |
| 17 | 12 | shadow live plant |
| 18 | 14 | Controller B enablement |
| 19 | 14 | final A/B wave 1 |
| 20 | 13 | final A/B wave 2 |
| 21 | 10 | soak / degraded cases |
| 22 | 10 | targeted evidence repair |
| 23 | 12 | demo hardening |
| 24 | 8 | final handover |
| **Total** | **276 h** | |

---

# 35. Personal gate responsibilities

## G0

Member A must prove:

- exact BOM understood;
- no old hardware assumptions.

---

## G1

Must prove:

- sensors;
- PZEM;
- IBT-2 default OFF;
- first safe TEC response.

---

## G2

Must prove:

- repeatable physical plant;
- safe operating envelope;
- fuse;
- physical SAFE_LOCAL feasibility.

---

## G3

Must sign off:

- dataset physical consistency;
- no material drift.

---

## G4

Must provide:

- physical response delay;
- final plant readiness;
- predictive actuation safe envelope.

---

## G5

Must provide:

- final A/B physical campaign validity.

---

## G6

Must provide:

- reproducible hardware handover.

---

# 36. Member A leader-review rubric

Leader should not ask only:

```text
“đã nối xong chưa?”
```

Review:

## Hardware

- exact item?
- safe?
- measured?

## Firmware

- identity stable?
- failure explicit?
- restart safe?

## Evidence

- quantitative?
- raw file?
- version?
- pass criterion?

## Handoff

- can B/C/D use it now?

## Risk

- what could invalidate downstream work?

---

# 37. Common failure patterns Member A must avoid

## 37.1 Generic TEC datasheet worship

Wrong:

```text
TEC1-12715 → 15 A by definition
```

Correct:

```text
measure exact purchased SKU
```

---

## 37.2 IBT-2 “43 A module” claim

Wrong.

43 A is related to BTS7960 chip current-limitation specification.

---

## 37.3 Sequential DS18B20 conversions

Wrong for ~1 Hz:

```text
750 ms × 3
```

Use shared conversion.

---

## 37.4 Sensor role by discovery index

Wrong:

```text
sensor[0] = T1
```

Use ROM mapping.

---

## 37.5 PZEM range not verified

Wrong.

50 A profile is a semantic prerequisite for current evidence.

---

## 37.6 PZEM = total system energy

Wrong.

It observes the defined cooling branch.

---

## 37.7 Command ACK = cooling

Wrong.

Need electrical + thermal response.

---

## 37.8 Fix repeatability with ML

Wrong.

Plant instability must be fixed/quantified physically.

---

## 37.9 Hide invalid runs

Wrong.

Every attempt stays in campaign log.

---

## 37.10 Reassemble before final A/B casually

Wrong.

Thermal contact changes plant behavior.

---

# 38. Physical evidence package structure

```text
evidence/A/
├─ W01/
├─ W02/
...
├─ W24/
├─ commissioning-index.md
├─ hardware-config/
├─ calibration/
├─ characterization/
├─ S1/
├─ S2/
├─ S4/
├─ AB-final/
└─ handover/
```

---

# 39. Final Member A defense anchors

Member A must answer clearly:

### Why three DS18B20?

> spatial state and gradient; A1 proves whether it adds predictive value.

### Why BME?

> environment/RH context, not product-quality ground truth.

### Why PZEM?

> command intent does not prove branch current; PZEM independently observes electrical response.

### Why shunt 50 A / 75 mV?

> exact purchased PZEM measurement configuration; profile must match 50 A range.

### Why not assume 15 A TEC current?

> seller/family name is not measured electrical behavior of exact SKU.

### Why one TEC?

> enough to study timing/verification while reducing nuisance asymmetry and hardware risk.

### Why 6 L?

> small repeatable cyber-physical research testbed, not warehouse emulator.

### Why not call temperature drop “COP”?

> COP requires heat-flow \(Q_c\), not merely ΔT divided by electrical power.

### Why does hot-side matter?

\[
Q_h=Q_c+P_{in}
\]

> it rejects both pumped and electrical heat.

---

# 40. Reference sources for Member A execution

**[R1] Analog Devices — DS18B20.**  
Official product/datasheet information: 1-Wire, unique 64-bit ROM, multidrop, ±0.5 °C specified range and programmable 9–12-bit resolution.  
https://www.analog.com/en/products/ds18b20.html

**[R2] Espressif Component Registry — DS18B20 driver.**  
Official Espressif component showing 1-Wire bus enumeration and DS18B20 device handling.  
https://components.espressif.com/components/espressif/ds18b20

**[R3] Bosch Sensortec — BME280.**  
Official humidity/temperature sensor specifications including ~1 s RH response and ±3 %RH tolerance under specified conditions.  
https://www.bosch-sensortec.com/en/products/environmental-sensors/humidity-sensors-bme280

**[R4] Analog Devices — MAX3485.**  
3.3 V RS-485/RS-422 transceiver, half-duplex family capability, 10 Mbps class.  
https://www.analog.com/en/products/max3485.html

**[R5] Espressif — UART / RS-485 programming guide.**  
ESP-IDF supports RS-485 half-duplex direction handling via UART modes.  
https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/uart.html

**[R6] Peacefair-style PZEM-017 manual mirror.**  
Modbus register and 50 A range profile information. The exact shipped unit/manual remains final revision authority.  
https://manuals.plus/ae/32913960037

**[R7] Infineon — BTS7960 Datasheet.**  
Half-bridge silicon features, logic inputs, protection, PWM capability and current-limit behavior.  
https://www.infineon.com/dgdl/BTS7960_Datasheet.pdf

**[R8] Espressif — ESP32-S3 Hardware Design Guidelines.**  
ESP32-S3R2 Quad-SPI PSRAM mapping, GPIO/strapping considerations and board-design constraints.  
https://documentation.espressif.com/esp-hardware-design-guidelines/en/latest/esp32s3/index.html

**[R9] Ferrotec — Thermoelectric Reference Guide.**  
Thermoelectric heat-pump fundamentals, heat-sink considerations and heat balance \(Q_h=Q_c+P_{in}\).  
https://thermal.ferrotec.com/technology/thermoelectric-reference-guide/

---

# 41. Final handover checklist

## Exact hardware

- [ ] BOM reconciled.
- [ ] no silent substitution.
- [ ] final hardware config ID.

## Sensor system

- [ ] ROM map.
- [ ] fixed positions.
- [ ] consistency report.
- [ ] degraded behavior.

## Electrical

- [ ] PZEM 50 A profile.
- [ ] OFF envelope.
- [ ] active current/power range.
- [ ] fuse rationale.
- [ ] power topology.
- [ ] default OFF proof.

## Thermal

- [ ] cooling polarity.
- [ ] cool-down/warm-up.
- [ ] response delay.
- [ ] recovery.
- [ ] gradient/repeatability.
- [ ] V1/hot-side limitations.

## Firmware

- [ ] coherent snapshot.
- [ ] boot ID / seq.
- [ ] quality.
- [ ] command/ACK.
- [ ] safe reset.

## Experiments

- [ ] S1 protocol.
- [ ] S2 protocol.
- [ ] S4 safe fault.
- [ ] A/B physical run ledger.
- [ ] invalid runs retained.

## Final

- [ ] demo runbook.
- [ ] evidence index.
- [ ] another member can reproduce physical startup.
- [ ] all limitations explicit.

---

# 42. North star

> **Member A succeeds when nobody downstream has to guess what the hardware did.**

> **Every useful ColdGuard result starts with a physical fact that can be traced to a known sensor, a known position, a known hardware configuration and a known measurement path. Every actuation claim ends only after the branch current and chamber response agree with the command.**

> **The strongest contribution of Member A is not a colder chamber. It is a trustworthy experimental plant.**
