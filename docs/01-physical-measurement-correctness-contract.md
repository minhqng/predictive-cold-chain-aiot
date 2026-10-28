# COLDGUARD — HỆ THỐNG BẢO VỆ CHUỖI LẠNH CHỦ ĐỘNG
## Physical & Measurement Correctness Contract · Hardware Integration · Safety Invariants

> **Document:** `docs/01-physical-measurement-correctness-contract.md`  
> **Course:** Internet of Things (IoT) — Course Project / Bài tập lớn  
> **Project:** **ColdGuard — Hệ thống bảo vệ chuỗi lạnh chủ động**  
> **Type:** Physical Domain Model + Measurement Contract + Hardware Correctness Specification + Safety Invariant Contract  
> **Status:** **PROPOSED FREEZE v1.0 — REVIEW CANDIDATE**  
> **Baseline date:** **2026-09-29**  
> **Parent:** `00-project-scope-architecture.md`  
> **Children:** `02-aiot-closed-loop-engineering.md`, `03-verification-experiments-demo.md`, `04-team-execution-plan.md`, `05A/05B/05C/05D`  
> **Normative role:** source of truth for physical vocabulary, hardware configuration semantics, sensor identity, measurement meaning, electrical/thermal state, physical authority, calibration semantics, legal actuator states, hardware safety invariants, degraded-state rules, commissioning-derived parameters, physical failure classification and the conditions under which ColdGuard data may be treated as valid evidence.  
> **Not source of truth for:** MQTT topic names, backend database schema, API routes, model hyperparameters, exact experiment repetition counts, team scheduling or individual weekly tasks. Those belong to Docs 02–05.  
> **BOM relationship:** the exact 24-item purchased BOM is frozen by Doc 00. This document mirrors that BOM only to define physical contracts. If the two tables ever differ, **Doc 00 wins and Doc 01 is invalid until corrected**.  
> **Executable source of truth:** firmware pin definitions, device configuration and calibration files may specify implementation-level detail after approved commissioning, but they MUST preserve this document’s physical meaning and invariants.  
> **Change policy:** any change to a physical sensor role, sensor position identity, current-shunt range, actuator direction, power topology, physical authority, measurement unit/meaning, calibration method, default-off behavior, safe-local physical boundary or accepted operating envelope requires updating this document before or together with the implementation.

> **Correctness thesis.**  
> **ColdGuard is physically correct only when software-visible state remains traceable to a known sensor or actuator boundary, commands cannot be confused with physical effects, unsafe or stale measurements cannot silently become control truth, and every claimed cooling action can be reconciled with both electrical evidence and thermal response under a versioned hardware configuration.**

---

# 0. Why this document exists

A cyber-physical IoT system can be perfectly implemented in software and still be physically wrong.

Examples:

```text
MQTT command says COOLING_ON
but IBT-2 never energizes the TEC.

PZEM reports current
but the cold side does not cool because heat rejection is poor.

Three temperature values exist
but sensor identities swap after reboot.

A dataset contains 100,000 rows
but sensor placement changed halfway through the campaign.

A model reports strong accuracy
but its input current field is scaled with the wrong shunt range.

ESP32 reports ACK
but command was stale and should never have been applied.

Temperature decreases for one run
but the hot-side assembly overheats and cannot repeat the result.
```

The purpose of this document is therefore not to describe cloud infrastructure.

It defines:

```text
what the physical system actually contains
what each measurement physically means
which observation is authoritative for which fact
which actuator states are legal
what must always remain safe
what makes a measurement valid or degraded
what conditions invalidate an experiment
what must be measured rather than assumed from seller listings
```

Everything in Doc 02 exists to transport, process or act on the contracts frozen here.

Everything in Doc 03 exists to prove them.

---

# 1. Correctness vocabulary

## 1.1 Physical fact

A **physical fact** is a state of the real testbed that exists independently of backend software.

Examples:

```text
T1 probe temperature
door contact open/closed
cooling-branch current
TEC physically energized
temperature recovering after disturbance
```

A database row may represent a physical fact.

It does not create that physical fact.

---

## 1.2 Observed state

**Observed state** is what a sensor or measurement path reports.

Example:

```text
PZEM current = 11.42 A
```

This is stronger than:

```text
cooling_command = ON
```

for the claim:

> electrical current flowed in the cooling branch.

Observed state is still subject to:

- calibration;
- sensor validity;
- communication integrity;
- timing;
- range/configuration correctness.

---

## 1.3 Commanded state

**Commanded state** is software intent.

Example:

```text
desired_cooling = ON
```

It does not prove:

- ESP accepted the command;
- driver enabled;
- current flowed;
- cooling was thermally effective.

---

## 1.4 Applied state

**Applied state** is the edge controller’s locally accepted and executed control state.

Example:

```text
applied_cooling = ON
```

Applied state is stronger than desired state, but still does not prove electrical power reached the TEC.

---

## 1.5 Electrical response

**Electrical response** is evidence from the measured cooling branch that the actuation path changed as expected.

Examples:

```text
branch current rises
branch power rises
branch voltage remains in plausible envelope
```

For ColdGuard, PZEM-017 + the frozen 50 A / 75 mV shunt is the primary branch-level electrical observation path.

---

## 1.6 Thermal response

**Thermal response** is a change in the measured thermal state consistent with the commanded cooling direction over a physically meaningful time window.

Example:

```text
cooling ON
→ electrical response valid
→ Tmean slope becomes more negative / recovery improves
```

Thermal response is not defined by one arbitrary sample.

It is evaluated over a window derived from plant characterization.

---

## 1.7 Verified physical action

A cooling action is **verified** only when the required evidence chain for that mode has been satisfied.

Core interpretation:

```text
valid fresh state
→ legal command
→ applied state
→ expected electrical response
→ expected thermal response
```

If electrical or thermal evidence is missing, the system must not silently label the action:

```text
SUCCESSFUL_COOLING
```

---

## 1.8 Authority

An **authority** is the strongest available source for deciding one fact.

Examples:

| Fact | Authority |
|---|---|
| physical sensor identity | frozen ROM/address mapping + physical label |
| T1/T2/T3 reading | corresponding DS18B20 measurement |
| door contact | MC-38 input |
| cooling-branch current/power | validated PZEM path |
| desired action | policy/command record |
| locally applied action | edge controller state |
| cooling actually produced electrical load | PZEM electrical response |
| cooling produced useful thermal effect | temperature trajectory |
| hardware configuration | versioned hardware configuration tied to Doc 00 |

---

## 1.9 Derived state

A **derived state** is computed from observations.

Examples:

```text
Tmean
Tmax
Tmin
thermal gradient
dT/dt
thermal exposure
risk score
cooling-health interpretation
```

Derived state is never allowed to erase provenance.

Every report-grade derived value must be reconstructable from:

```text
raw input
+
time window
+
algorithm/version
```

---

## 1.10 Valid measurement

A **valid measurement** satisfies all required conditions for its intended use:

- source identity known;
- timestamp/sequence acceptable;
- sensor/configuration known;
- value parses correctly;
- value within physical/configured sanity range;
- no active quality flag that forbids the use;
- calibration/provenance adequate for the claim.

A measurement can be valid for visualization but invalid for predictive control.

---

## 1.11 Degraded measurement

A **degraded measurement** is still observable but has reduced trust.

Examples:

- one of three DS18B20 probes temporarily unavailable;
- PZEM timeout while thermal sensors remain healthy;
- BME280 unavailable;
- timestamp uncertainty after reconnect.

Degraded state must be explicit.

---

## 1.12 Invalid measurement

An **invalid measurement** must not be used as if it were a normal physical observation.

Examples:

- CRC failure;
- impossible/unparseable value;
- unknown sensor ROM assigned to T1/T2/T3;
- PZEM configured for the wrong shunt profile;
- stale sample beyond control freshness policy;
- run uses unknown hardware configuration.

---

## 1.13 Calibration

**Calibration** is a documented mapping/check between instrument output and a defined reference/procedure.

ColdGuard distinguishes:

```text
factory datasheet specification
≠
module/probe calibration
≠
cross-check
≠
field sanity check
```

Do not call a casual comparison “calibration” if no reference procedure is defined.

---

## 1.14 Characterization

**Characterization** means empirically determining how the actual purchased testbed behaves.

Examples:

- TEC current at 12 V;
- cooling-branch power;
- IBT-2 temperature;
- chamber cool-down curve;
- disturbance recovery;
- healthy electrical envelope;
- thermal-response delay;
- PZEM behavior under PWM.

Characterization does not change the BOM.

It converts unknown parameters into measured configuration.

---

## 1.15 Safety invariant

A **safety invariant** is a condition that must never be intentionally violated during valid operation.

Example:

```text
TEC can be energized
⇒
hot-side fan must be operating/available according to the frozen V1 integration contract
```

If an invariant cannot be proven with the purchased hardware, the relevant gate fails.

The project does not silently add substitute hardware to make the test pass.

---

## 1.16 Liveness obligation

A **liveness obligation** states that useful progress should eventually occur when required dependencies recover.

Example:

```text
if network returns
and device/backend remain operational
then current device state should eventually resynchronize
```

Liveness never overrides safety.

---

## 1.17 Evidence-grade run

An **evidence-grade run** is a physical experiment whose:

- hardware configuration is known;
- sensor placement is frozen;
- calibration status is known;
- data capture is sufficiently complete;
- disturbance/action protocol is known;
- validity criteria pass.

A run can exist in the database without being evidence-grade.

---

# 2. Physical modeling principles

## 2.1 Separate intent, electricity and thermodynamics

ColdGuard uses three distinct correctness boundaries:

```text
software intent
      ↓
electrical effect
      ↓
thermal effect
```

No one boundary substitutes for another.

---

## 2.2 Prefer measured module behavior over generic Internet assumptions

The project contains commercial modules whose exact implementation can vary:

- dual ESP32-S3R2 board;
- waterproof DS18B20 probes;
- BME280 breakout module;
- PZEM-017 module/revision;
- MAX3485 breakout;
- IBT-2 board;
- TEC1-12715 seller SKU;
- V1 thermal assembly.

Therefore:

```text
IC datasheet
≠
finished module guarantee
```

unless the exact module manufacturer documents the whole assembly.

---

## 2.3 Keep physical authority local to the phenomenon

Examples:

```text
backend says ON
```

does not decide current.

```text
PZEM says current
```

does not decide useful cooling.

```text
temperature falls
```

does not alone prove which electrical component caused it.

Correctness uses the strongest source for each claim.

---

## 2.4 Preserve sensor identity across reboots

T1/T2/T3 are physical roles, not array indices.

A reboot must not change:

```text
ROM A → T1
ROM B → T2
ROM C → T3
```

without an explicit hardware-configuration change.

---

## 2.5 Physical position is part of configuration

Sensor placement affects data semantics.

Therefore:

```text
sensor identity
+
sensor position
```

together define a channel.

Changing a probe from:

```text
near door
```

to:

```text
near cold plate
```

changes the experiment configuration even if the ROM ID remains the same.

---

## 2.6 Do not let derived values hide missing raw channels

If T3 is unavailable:

```text
Tmean = mean(T1,T2)
```

must not silently use the same semantic label as:

```text
Tmean = mean(T1,T2,T3)
```

unless the definition explicitly supports degraded mode and records it.

---

## 2.7 Physical comparison requires configuration comparability

A/B runs are not directly comparable if one run changes:

- TEC;
- V1 mounting;
- shunt range;
- sensor position;
- chamber geometry;
- fan behavior;
- hardware revision;

without an explicit block/stratification rule.

---

# 3. Canonical purchased hardware configuration

## 3.1 Authoritative BOM mirror

This table mirrors Doc 00 exactly.

| ID | Linh kiện | Frozen purchased specification | Quantity |
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

## 3.2 BOM checksum rule

Every evidence-grade run records:

```text
hardware_config_id
```

A hardware configuration record must at minimum resolve to the above 24 IDs.

No downstream code may silently interpret:

```text
HW-v1
```

as a different BOM.

---

## 3.3 No silent additions

The following are not part of P0:

- internal circulation fan;
- fourth DS18B20 product proxy;
- current sensor other than PZEM-017;
- second TEC;
- additional MOSFET driver;
- extra power supply;
- external ADC;
- logic level shifter;
- arbitrary protection electronics not frozen in the purchased list.

If commissioning proves an additional component is required for safe operation:

> **the gate fails and the team performs an explicit BOM/configuration change.**

It is not acceptable to wire in an extra component and keep calling the setup the same hardware configuration.

---

## 3.4 No silent removal

Likewise, do not remove:

- the shunt;
- PZEM;
- MC-38;
- any of the three DS18B20 sensors;

from evidence-grade core experiments while still claiming the full P0 hardware configuration.

Ablation experiments may intentionally omit a signal logically, but physical configuration remains recorded.

---

# 4. Canonical physical subsystem map

| Subsystem | Hardware | Physical responsibility |
|---|---|---|
| Temperature Sensing | DS18B20 ×3 | spatial thermal state |
| Environmental Sensing | BME280 | local air temperature/RH context |
| Door Monitoring | MC-38 | disturbance/contact context |
| Electrical Observation | PZEM-017 + 50 A/75 mV shunt | branch V/I/P/Wh |
| RS-485 Interface | MAX3485 3.3 V module | UART ↔ differential RS-485 |
| Edge Controller | one primary ESP32-S3R2 on dual board | sensing, local state, communication, control |
| Power Control | BTS7960/IBT-2 | switching/drive path |
| Cooling Actuator | exact purchased TEC1-12715 | thermoelectric heat pumping |
| Thermal Assembly | V1 12 V | cold-side/hot-side transfer + forced-air rejection |
| Testbed | HS2 6 L | controlled thermal environment |
| Main Power | 12 V / 33 A PSU | DC energy source |
| Logic Power | XL4015 | 12 V → 5 V logic |
| Protection | ATO fuse box + purchased fuse set | branch overcurrent protection |
| Distribution | TB4504 45 A 4P | high-current distribution |
| Auxiliary Connection | PCT218 + jumper/header | low-current signal/auxiliary connections |

---

# 5. Thermal testbed contract

## 5.1 Chamber identity

The physical testbed is:

```text
HS2
nominal volume = 6 L
quantity = 1
```

The project does not claim that the chamber reproduces:

- commercial cold-room airflow;
- reefer container wall construction;
- pallet thermal mass;
- warehouse door size;
- production refrigeration dynamics.

---

## 5.2 Chamber role

The chamber exists to provide:

- a bounded physical environment;
- repeatable disturbance;
- measurable cooling/recovery;
- manageable experimental cycle time.

It is a **research testbed**.

---

## 5.3 Chamber geometry is configuration

Evidence-grade experiments freeze:

- sensor mounting points;
- cold-side assembly location;
- door direction/closure;
- cable penetration/sealing;
- internal contents.

If geometry changes materially:

```text
hardware_config_id or experiment_block
```

must change.

---

## 5.4 Air-only thermal capacity is not the plant model

For scale intuition only:

\[
V\approx0.006\,m^3
\]

At approximately:

\[
\rho_{air}\approx1.2\,kg/m^3
\]

the air mass is:

\[
m\approx0.0072\,kg
\]

At:

\[
c_p\approx1005\,J/(kg\cdot K)
\]

a 10 K air-only sensible change is roughly:

\[
Q\approx72\,J
\]

This does not represent the full chamber energy.

Real behavior includes:

- walls;
- V1;
- TEC;
- moisture;
- infiltration;
- wiring;
- internal contents;
- ambient coupling.

No control model may use the `72 J` figure as a complete plant energy model.

---

# 6. DS18B20 contract

## 6.1 Manufacturer-level facts

Analog Devices documents the DS18B20 IC with:

- 1-Wire interface;
- multidrop support;
- unique 64-bit ROM;
- programmable 9–12-bit resolution;
- −55…125 °C measurement range;
- ±0.5 °C accuracy from −10…85 °C.

These specifications apply to the IC under datasheet conditions.

The team's waterproof 1 m assemblies still require system-level verification.

---

## 6.2 Power mode

P0 preferred mode:

```text
normal powered 3-wire operation
VDD
GND
DQ
```

Parasite-power operation is not required for the project.

---

## 6.3 Bus topology

All three probes may share one 1-Wire data bus.

Frozen resistor:

```text
4.7 kΩ pull-up
```

to 3.3 V according to the purchased BOM.

The exact bus length/branch topology is an implementation detail, but evidence-grade operation requires reliable discovery/read/CRC behavior.

---

## 6.4 Sensor roles

Canonical position semantics:

```text
T1 = near-door region
T2 = central region
T3 = far/opposite region
```

Final exact mounting coordinates/fixture description are frozen during commissioning.

---

## 6.5 Identity contract

Each physical probe is identified by its unique ROM code.

A configuration table must exist:

| Logical role | ROM ID | Physical label | Position |
|---|---|---|---|
| T1 | frozen after discovery | label | near door |
| T2 | frozen after discovery | label | center |
| T3 | frozen after discovery | label | far/opposite |

The order returned by a library is not identity.

---

## 6.6 DS18B20 correctness invariants

### PHY-DS-001 — Three unique roles

```text
T1, T2, T3
```

must map to three distinct physical ROM IDs.

### PHY-DS-002 — No implicit remap

An unknown ROM after reboot does not automatically replace a missing known sensor.

### PHY-DS-003 — Position stability

Moving a probe materially changes configuration.

### PHY-DS-004 — Raw failure visibility

CRC/read failure must be represented as invalid/missing.

It must not become:

```text
0 °C
previous value pretending to be current
silent interpolation
```

for control.

### PHY-DS-005 — No wall/cold-plate contact for air channels

T1/T2/T3 represent chamber air-region measurements.

Their sensing tips must not intentionally contact:

- chamber wall;
- cold plate;
- TEC;
- hot-side assembly.

### PHY-DS-006 — Shared conversion semantics

A valid acquisition strategy should avoid treating sequential conversion delay as three simultaneous physical times.

Preferred:

```text
broadcast Convert T
→ wait for conversion
→ read scratchpads
```

when supported by the bus implementation.

---

## 6.7 Sampling target

P0 target:

```text
approximately 1 Hz effective thermal telemetry
```

The exact acquisition cycle may be slightly longer/shorter depending on selected resolution and bus handling.

The key contract is:

- timestamps represent actual observation time semantics;
- no fake 1 Hz duplicates.

---

## 6.8 Missing-sensor degraded state

If exactly one DS18B20 is temporarily invalid:

```text
thermal_state_quality = DEGRADED
```

The system may continue minimum local protection using the remaining trusted sensors according to Doc 02/06 policy.

Predictive inference may be disabled unless the model explicitly supports that missing-channel state.

If multiple key thermal sensors fail:

```text
predictive actuation prohibited
```

and fallback becomes conservative according to the control contract.

---

# 7. BME280 contract

## 7.1 Hardware role

Frozen hardware:

```text
BME280
I²C
3.3 V module
quantity = 1
```

Bosch documents the IC:

- VDD 1.71–3.6 V;
- VDDIO 1.2–3.6 V;
- I²C/SPI;
- temperature range −40…85 °C;
- humidity accuracy tolerance around ±3 %RH;
- humidity response time τ63% ≈1 s.

---

## 7.2 Semantic role

Canonical fields:

```text
t_air_context
rh
```

BME280 is not a replacement for T1/T2/T3.

Its primary value is contextual:

- ambient/chamber air context;
- humidity dynamics;
- condensation-related interpretation;
- extra state feature.

---

## 7.3 Integration caveat

A sensor measures the environment at its own physical package.

Nearby:

- electronics heat;
- stagnant pocket;
- cold plate;
- condensation;
- direct fan jet;

can bias the reading.

Therefore mounting location is part of the configuration.

---

## 7.4 Pressure

BME280 includes pressure sensing.

Pressure is **not a P0 research feature** unless a later documented question requires it.

Do not add pressure to the model merely because the sensor exposes it.

---

## 7.5 BME280 failure semantics

Loss of BME280 does not automatically invalidate basic thermal protection if DS18B20 channels remain valid.

It does invalidate claims requiring:

- RH;
- BME context;
- BME ablation.

---

# 8. MC-38 door contract

## 8.1 Role

MC-38 is a reed-switch contact.

It provides event/context state:

```text
DOOR_OPEN
DOOR_CLOSED
```

subject to actual polarity mapping.

---

## 8.2 Polarity must be commissioned

The project must not assume:

```text
GPIO HIGH = OPEN
```

or:

```text
GPIO LOW = OPEN
```

without physical verification.

Frozen configuration records:

```text
raw electrical state
→ semantic OPEN/CLOSED
```

---

## 8.3 Debounce

Mechanical contact may bounce.

Firmware may debounce the input.

Debounce must not erase a deliberately controlled door-open interval.

---

## 8.4 Door-event identity

Experiment records should preserve:

- transition time;
- resulting state;
- duration when derivable.

For controlled disturbance:

```text
door-open duration
```

is part of the experimental treatment.

---

## 8.5 Door correctness invariants

### PHY-DOOR-001

Door event is context, not temperature authority.

### PHY-DOOR-002

A missing door sensor must not be silently interpreted as CLOSED.

### PHY-DOOR-003

Final experiment protocol must define how the physical door is opened/closed reproducibly.

---

# 9. PZEM-017 electrical-observation contract

## 9.1 Role

Frozen:

```text
PZEM-017
RS-485 / Modbus
quantity = 1

external shunt
50 A / 75 mV
quantity = 1
```

The measurement scope is:

> **cooling branch**

not total-system power.

---

## 9.2 Canonical signals

```text
cooling_voltage_V
cooling_current_A
cooling_power_W
cooling_energy_counter_Wh
```

Canonical report wording:

```text
Cooling-branch Power
Cooling-branch Energy
```

Do not report:

```text
Total System Power
```

unless all relevant loads are proven to be inside that measurement boundary.

---

## 9.3 Manual-derived register semantics

The PZEM-017 manual in circulation documents:

| Register | Meaning | Resolution |
|---|---|---|
| `0x0000` input | voltage | 0.01 V |
| `0x0001` input | current | 0.01 A |
| `0x0002..0x0003` | power | 0.1 W |
| `0x0004..0x0005` | energy | 1 Wh |

Configuration register:

```text
0x0003 current range
0x0000 = 100 A
0x0001 = 50 A
0x0002 = 200 A
0x0003 = 300 A
```

ColdGuard must verify:

```text
current range = 50 A profile
```

before evidence-grade current/power data are accepted.

---

## 9.4 Serial revision rule

Current manual mirrors describe newer units as:

```text
9600 baud
8 data bits
no parity
1 stop bit
```

Other circulated manuals/modules document:

```text
2 stop bits
```

Therefore:

### PHY-PZ-001 — Revision-aware serial configuration

Serial framing is a commissioning parameter.

Do not label the module failed until:

- A/B polarity checked;
- communication-side power checked;
- slave address checked;
- CRC checked;
- 8N1 / documented shipped revision tested.

---

## 9.5 Communication-side power

The frozen hardware plan supplies the PZEM communication interface from the 5 V logic rail.

The team must follow the actual shipped module terminal/manual markings.

Do not route 5 V into the 3.3 V MAX3485 VCC.

---

## 9.6 Shunt semantics

Frozen shunt:

\[
I_{rated}=50\,A
\]

\[
V_{shunt,rated}=75\,mV
\]

Equivalent:

\[
R_s=\frac{0.075}{50}=1.5\,m\Omega
\]

Expected low-side drop examples:

| Current | Drop |
|---:|---:|
| 5 A | 7.5 mV |
| 10 A | 15 mV |
| 15 A | 22.5 mV |
| 20 A | 30 mV |

These are derived circuit values, not measurements.

---

## 9.7 Shunt dissipation

\[
P_{shunt}=I^2R_s
\]

Examples:

| Current | Approx. dissipation |
|---:|---:|
| 5 A | 0.0375 W |
| 10 A | 0.15 W |
| 15 A | 0.3375 W |
| 20 A | 0.60 W |

The shunt/terminal installation still requires physical inspection because connection resistance can dominate the ideal shunt loss.

---

## 9.8 PZEM placement boundary

The PZEM/shunt path must observe the intended TEC/driver cooling branch consistently across runs.

Changing what loads are included in the branch changes the metric.

---

## 9.9 PZEM evidence limitations

PZEM is appropriate for:

- average/slow branch voltage/current/power;
- energy integration;
- actuator-response verification.

PZEM is not treated as:

- oscilloscope;
- cycle-by-cycle PWM current probe;
- high-speed transient instrument.

---

## 9.10 PWM warning

The manual does not sufficiently specify the internal averaging behavior for the team's exact PWM-driven TEC waveform.

Therefore:

### PHY-PZ-002

PZEM power under PWM is **characterization-required** before becoming a primary energy claim.

Until then:

```text
power under steady/full ON
```

has stronger semantic status than:

```text
instantaneous PWM power
```

for research reporting.

---

## 9.11 Cross-check requirement

Before final campaign, current/power should be plausibility-checked against an independent trusted reference method available to the team.

Doc 03 defines the exact procedure.

If no suitable reference is available:

> report PZEM measurements with the limitation; do not invent calibration accuracy.

---

# 10. MAX3485 / RS-485 contract

## 10.1 Manufacturer facts

Analog Devices specifies MAX3485 as:

- 3.3 V powered;
- half-duplex RS-485/RS-422 transceiver;
- 10 Mbps class;
- driver/receiver enable;
- up to 32 transceivers on the bus.

ColdGuard uses only one PZEM node.

Bandwidth is not a constraint.

---

## 10.2 Signal roles

Conceptual:

```text
ESP UART TX → DI
RO → ESP UART RX
GPIO direction → DE / /RE
A/B ↔ PZEM A/B
```

Exact purchased-module pin labels must be visually verified.

---

## 10.3 Direction state

Half-duplex operation requires correct direction switching.

Conceptual states:

```text
TRANSMIT:
DE enabled
receiver state according to implementation

RECEIVE:
driver disabled
receiver enabled
```

A firmware timing bug may appear as:

- no reply;
- truncated reply;
- CRC errors.

---

## 10.4 Differential wiring

A/B should be routed together where practical and kept away from noisy high-current/PWM wiring.

Do not use the presence of MAX3485 as proof that any arbitrary wiring is noise-immune.

---

# 11. ESP32-S3R2 board contract

## 11.1 Frozen board

```text
Dual ESP32-S3R2 + W25Q32 + CH343G
quantity = 1
```

The exact board schematic is not currently treated as an official manufacturer reference.

Therefore chip-level facts and board-level facts are kept separate.

---

## 11.2 S3R2 memory fact

Espressif documentation identifies ESP32-S3R2 as:

```text
2 MB in-package Quad SPI PSRAM
```

This matters because octal PSRAM pin restrictions do not automatically apply to R2.

---

## 11.3 GPIO restriction facts

ESPressif documents:

```text
GPIO0, GPIO3, GPIO45, GPIO46
```

as strapping pins.

It also documents GPIO26–32 as commonly used for SPI0/1 flash/PSRAM and not recommended for arbitrary reuse.

For Octal flash/PSRAM variants such as S3R8/R8V, GPIO33–37 are additionally used by the 8-line memory bus.

S3R2 uses Quad in-package PSRAM, so the specific octal restriction on GPIO33–37 does not arise from the S3R2 PSRAM itself.

However:

> **the custom dual-board routing can still use those pins for other onboard functions.**

---

## 11.4 Board-level authority

Final GPIO availability is determined by:

1. exact board documentation if available;
2. board silkscreen/schematic;
3. continuity/bring-up evidence;
4. successful peripheral test.

Chip datasheet alone is insufficient.

---

## 11.5 Primary-MCU role

P0 uses one MCU as primary controller.

Current convention:

```text
right-hand MCU preferred
```

until the actual board is inspected and labeled consistently.

The identity must then be frozen in hardware configuration.

---

## 11.6 Secondary MCU

The other S3R2 remains:

```text
unused / spare / optional future extension
```

in P0.

It must not generate duplicate control authority.

---

## 11.7 Proposed GPIO mapping v1

> **SUPERSEDED 2026-10-28** — bảng dưới đây là lịch sử. Bản đồ chân hiệu lực là
> `evidence/A/as-built-pinmap-2026-10-27.md` (map v2, `CG_PIN_MAP_VERSION = 2`):
> DS18B20=GPIO33, BME280 SDA/SCL=21/34, MC-38=GPIO35, RS-485 TX/RX=36/37 (AUTO,
> không DE/RE), IBT-2 RPWM/R_EN/L_EN=5/6/10, LPWM=GND. Xung đột GPIO10
> (DS18B20 cũ vs L_EN as-built) được giải quyết bằng cách chuyển DS18B20 sang 33.
> Không xoá bảng gốc; chỉ thêm ghi chú này.

Subject to board verification:

| Function | Proposed GPIO |
|---|---:|
| DS18B20 DATA | GPIO10 |
| BME280 SDA | GPIO21 |
| BME280 SCL | GPIO33 |
| MC-38 | GPIO34 |
| MAX3485 DE+/RE | GPIO35 |
| UART TX → MAX3485 DI | GPIO36 |
| UART RX ← MAX3485 RO | GPIO37 |
| IBT-2 cooling PWM | GPIO5 |
| IBT-2 enable | GPIO6 |

This is a **proposed firmware mapping**, not an immutable BOM item.

If board-level routing forces a change:

```text
pin_map_version
```

changes while BOM remains the same.

---

## 11.8 Boot/default-state contract

At reset and boot, the edge controller must not intentionally energize the cooling branch before:

- GPIO mode initialized;
- safety state initialized;
- actuator policy initialized.

If the actual IBT-2 board cannot remain safely OFF with the purchased configuration:

> Gate fails; do not silently add hardware while retaining the same configuration ID.

---

# 12. IBT-2 / BTS7960 actuation contract

## 12.1 Silicon versus module

Infineon BTS7960 is a high-current half-bridge IC.

The purchased IBT-2 is a module containing two half-bridge devices plus board-level implementation.

Therefore:

```text
BTS7960 datasheet limit
≠
IBT-2 module continuous-current rating
```

---

## 12.2 Datasheet-level facts

Infineon documents:

- high-current half bridge;
- logic-level control;
- protection functions;
- PWM capability up to approximately 25 kHz;
- current limitation with values depending strongly on junction temperature and side.

A commonly quoted `43 A` figure is associated with current-limitation behavior under specified conditions.

It is **not** a guarantee of continuous 43 A module operation.

---

## 12.3 ColdGuard operating mode

Normal ColdGuard operation does not require heating/reversal.

P0 fixes one polarity as:

```text
COOLING_DIRECTION
```

The reverse direction is not used in ordinary control.

---

## 12.4 Logical inputs

IBT-2 commonly exposes:

```text
RPWM
LPWM
R_EN
L_EN
R_IS
L_IS
VCC
GND
```

The actual purchased board labels are the final authority.

ColdGuard concept:

- one PWM direction used for cooling;
- opposite PWM held inactive;
- enable controlled;
- diagnostic `IS` pins not required for P0 because PZEM is the frozen branch feedback.

---

## 12.5 Logic voltage

IBT-2 logic rail is planned at 5 V.

ESP32 control is 3.3 V.

Chip-level BTS7960 input thresholds are compatible with logic-high around this range, but the IBT-2 module may include buffer logic.

Therefore 3.3 V drive compatibility is a commissioning result.

Do not add a level shifter silently.

---

## 12.6 Default-OFF invariant

### PHY-ACT-001

```text
BOOT or RESET
⇒
cooling output remains physically OFF
```

until the controller intentionally enables it.

Test must include:

- cold boot;
- reset;
- firmware restart if practical.

---

## 12.7 Enable invariant

### PHY-ACT-002

A PWM signal alone must not accidentally imply enabled output if the design contract expects a separate enable.

The applied-state representation must match actual pin state.

---

## 12.8 Direction invariant

### PHY-ACT-003

P0 must never unintentionally reverse the TEC polarity.

Reverse heating is outside normal control.

---

## 12.9 Thermal module protection

### PHY-ACT-004

If IBT-2/module temperature becomes abnormal during characterization:

```text
stop/invalidate the operating point
```

Do not interpret thermal shutdown as a valid controller behavior.

---

# 13. TEC1-12715 contract

## 13.1 SKU identity

Frozen item:

```text
TEC1-12715
exact purchased product/SKU
quantity = 1
```

The commercial family name is not treated as an exact electrical datasheet.

---

## 13.2 Prohibited generic assumptions

Do not freeze the following from random seller listings:

```text
Imax = exactly 15 A
Vmax = exactly 15.4 V
Qmax = exactly 150 W
R = fixed generic value
```

unless the exact purchased item is documented by a trusted manufacturer and verified.

---

## 13.3 Commissioning-derived parameters

Required:

- physical dimensions;
- polarity/cooling direction;
- current at selected operating points;
- branch voltage;
- input power;
- cold-side response;
- hot-side response;
- stable operating region.

---

## 13.4 Thermoelectric physics contract

Ferrotec's thermoelectric reference gives:

\[
P_{in}=V_{in}I
\]

and:

\[
Q_h=Q_c+P_{in}
\]

where:

- \(Q_c\) is heat pumped from the cold side;
- \(Q_h\) is heat rejected at the hot side.

Therefore:

### PHY-TEC-001

Hot-side assembly must reject both:

```text
pumped heat
+
electrical input heat
```

The hot side can be a stronger bottleneck than PSU nameplate power.

---

## 13.5 Polarity

During first low-power test:

- confirm which physical face becomes cold;
- record wiring polarity;
- freeze that orientation.

Do not infer orientation from wire color alone.

---

## 13.6 Thermal contact

Both faces require appropriate thermal interface to the V1 assembly.

Frozen thermal paste is the paste included with V1.

Application should be:

- thin;
- continuous;
- even;
- free of gross voids.

Mechanical pressure should be even.

---

# 14. V1 thermal assembly contract

## 14.1 Role

V1 12 V assembly provides:

- cold-side heat collection/spreading;
- hot-side heat rejection;
- forced air via fan.

Seller power claims are not proof of actual performance.

---

## 14.2 Orientation

Conceptually:

```text
inside chamber
→ cold side
→ thermal interface
→ TEC
→ thermal interface
→ hot side
→ fan
→ ambient outside chamber
```

---

## 14.3 Fan invariant

### PHY-TH-001

Whenever the TEC may be energized:

```text
hot-side fan must be operating/available
```

according to the frozen wiring mode.

If the fan is powered independently and continuously during experiments, that behavior must be recorded.

---

## 14.4 Hot-side rejection invariant

### PHY-TH-002

A run is not evidence-grade if hot-side thermal behavior enters an uncharacterized/unsafe region that causes:

- thermal shutdown;
- severe performance collapse;
- connector/assembly abnormality.

---

## 14.5 Seal/interface

The chamber penetration around V1 must be physically stable and sealed enough that run-to-run leakage does not dominate the experiment.

---

# 15. Power architecture contract

## 15.1 Main supply

Frozen:

\[
12\,V,\ 33\,A
\]

Ideal nameplate:

\[
P=396\,W
\]

This is not the project's measured consumption.

---

## 15.2 Branches

At minimum:

```text
main 12 V
├─ TEC / IBT-2 branch
├─ V1 fan branch
└─ logic 5 V branch via XL4015
```

---

## 15.3 TEC branch

Conceptual:

```text
PSU+
→ ATO fuse
→ IBT-2 supply
→ TEC through H-bridge
→ driver return
→ 50 A shunt according to PZEM wiring
→ PSU-
```

Exact PZEM sense terminals follow the shipped module manual.

---

## 15.4 Fan branch

V1 fan:

```text
12 V
→ auxiliary protection
→ fan
```

Fan must not depend on backend/cloud availability.

---

## 15.5 Logic branch

```text
12 V
→ auxiliary fuse
→ XL4015
→ 5 V
```

5 V planned loads include:

- PZEM communication side;
- IBT-2 logic;
- other frozen 5 V module needs.

ESP32 development power path must avoid unknown back-power behavior on the custom board.

---

## 15.6 XL4015 invariant

### PHY-PWR-001

XL4015 is not the TEC supply.

It is logic power conversion.

---

## 15.7 Distribution components

### TB4504

Intended for the higher-current distribution path within its actual terminal/rating limits.

### PCT218

Intended for low-current signal/auxiliary distribution.

### PHY-PWR-002

PCT218 must not become the main TEC current path.

---

## 15.8 Wire classes

Frozen:

```text
2×2.5 mm² ≈ high-current power wiring
2×0.75 mm² ≈ fan/auxiliary power
jumpers ≈ logic/signal
```

### PHY-PWR-003

Dupont/jumper wire must not carry the primary TEC current.

---

# 16. Fuse contract

## 16.1 Purchased options

TEC fuse set:

```text
10 A
15 A
20 A
```

Auxiliary:

```text
5 A
quantity ≥2
```

---

## 16.2 Final TEC fuse is commissioning-derived

Do not freeze:

```text
15 A
```

merely because the TEC commercial name contains `12715`.

Final choice must consider:

- measured steady current;
- startup/transient behavior;
- wire;
- fuse holder;
- IBT-2;
- terminal temperature;
- safe margin.

---

## 16.3 Fuse location

Protection should be near the source of the branch it protects.

---

## 16.4 Fuse invariant

### PHY-FUSE-001

No evidence-grade powered TEC test bypasses the intended branch fuse.

---

## 16.5 Fuse selection is not “largest that does not blow”

The objective is protection, not merely test continuity.

---

# 17. Measurement units and canonical semantics

## 17.1 Temperature

Canonical storage/report unit:

```text
°C
```

Do not mix raw integer units and °C without schema/version.

---

## 17.2 Relative humidity

Canonical:

```text
%RH
```

No conversion to an invented “moisture quality score” in the physical layer.

---

## 17.3 Voltage

Canonical:

```text
V
```

PZEM raw resolution:

```text
0.01 V
```

per circulated manual.

---

## 17.4 Current

Canonical:

```text
A
```

PZEM raw resolution:

```text
0.01 A
```

with 50 A profile.

---

## 17.5 Power

Canonical:

```text
W
```

PZEM resolution:

```text
0.1 W
```

---

## 17.6 Energy

Canonical:

```text
Wh
```

for stored/reported cooling-branch energy.

For numerical analysis, conversion to joules is:

\[
1 Wh=3600 J
\]

---

## 17.7 Door

Canonical semantic enum:

```text
OPEN
CLOSED
UNKNOWN
```

Do not expose raw GPIO level as the domain meaning.

---

## 17.8 Cooling state

At minimum:

```text
OFF
ON
```

If PWM is enabled:

```text
duty ∈ validated range
```

The exact electrical waveform remains implementation detail.

---

# 18. Time semantics

## 18.1 Three relevant times

For one measurement/event distinguish:

```text
captured_at
received_at
persisted_at
```

They are not interchangeable.

---

## 18.2 Edge-captured physical time

Where feasible, physical samples are timestamped at or near edge acquisition.

Backend receive time is not a substitute for physical sample time during network delay.

---

## 18.3 Sequence

Device telemetry must carry a monotonic sequence within a boot/session context.

Concept:

```text
boot_id + seq
```

helps distinguish:

- duplicate;
- delayed;
- rebooted device.

Exact schema belongs to Doc 02.

---

## 18.4 Stale data

A stale value can remain historically valid but be invalid for control.

Therefore:

```text
historical validity
≠
control freshness
```

Control freshness threshold belongs to policy configuration.

---

## 18.5 Clock uncertainty

If the edge clock is not synchronized:

- record uptime/sequence;
- record synchronization state;
- do not manufacture false timestamp precision.

---

# 19. Data quality states

Recommended physical-quality enum:

```text
VALID
DEGRADED
INVALID
UNKNOWN
```

---

## 19.1 VALID

All mandatory sources for the intended computation satisfy quality/freshness conditions.

---

## 19.2 DEGRADED

Some non-critical or redundant source is unavailable, but a defined degraded path remains legal.

---

## 19.3 INVALID

The state must not drive the intended predictive/control action.

Examples:

- unknown DS18B20 identity;
- wrong PZEM range;
- multiple key sensors failed;
- corrupted payload;
- configuration mismatch.

---

## 19.4 UNKNOWN

The system cannot determine state confidently enough to choose normal operation.

Unknown must not silently become normal.

---

# 20. Derived thermal-state contract

## 20.1 Mean

\[
T_{mean}=\frac{T_1+T_2+T_3}{3}
\]

only for full three-sensor valid state unless a separate degraded definition is explicitly versioned.

---

## 20.2 Max/min

\[
T_{max}=\max(T_1,T_2,T_3)
\]

\[
T_{min}=\min(T_1,T_2,T_3)
\]

---

## 20.3 Gradient

\[
G_T=T_{max}-T_{min}
\]

Unit:

```text
°C
```

Interpretation:

spatial spread proxy.

Not:

- heat flux;
- product quality;
- thermal resistance.

---

## 20.4 Standard deviation

A spatial standard deviation may be derived.

It must state whether population or sample formula is used.

---

## 20.5 Slope

A past-only temperature slope:

\[
\dot T \approx \frac{\Delta T}{\Delta t}
\]

must define:

- which temperature representation;
- window length;
- fit/filter method.

One `dT/dt` field without window/version is ambiguous.

---

## 20.6 Recovery slope

Recovery is evaluated only after a defined disturbance/action reference.

Do not compute arbitrary “recovery” continuously and treat it as ground truth.

---

# 21. Thermal exposure contract

Candidate:

\[
E_T=\sum_i \max(0,T_i-T_{limit})\Delta t
\]

where the exact representative temperature `T_i` must be frozen in Doc 03.

Potential choices include:

- `Tmean`;
- `Tmax`;
- named sensor;
- other predeclared quantity.

Do not switch the temperature definition after seeing results.

---

# 22. Electrical-state contract

## 22.1 Commanded OFF + near-zero current

Candidate normal state:

```text
command = OFF
current within validated off/noise envelope
```

Threshold is measured, not guessed.

---

## 22.2 Commanded ON + current in healthy envelope

Candidate electrically applied state.

Healthy envelope is commissioning-derived.

---

## 22.3 Commanded ON + current absent

Candidate:

```text
ACTUATOR_POWER_RESPONSE_MISSING
```

Do not immediately call it:

```text
TEC_BROKEN
```

Possible causes include:

- driver not enabled;
- fuse/open circuit;
- wiring;
- PZEM issue;
- TEC branch issue.

---

## 22.4 Commanded OFF + unexpected current

Candidate:

```text
CONTROL_ELECTRICAL_ANOMALY
```

This is high severity because it indicates physical energization outside expected intent.

---

# 23. Cooling-health contract

Canonical P0 diagnosis states:

```text
HEALTHY_RESPONSE
ELECTRICAL_RESPONSE_MISSING
THERMAL_EFFECTIVENESS_DEGRADED
CONTROL_ELECTRICAL_ANOMALY
UNKNOWN
```

---

## 23.1 HEALTHY_RESPONSE

Requires:

- valid applied command;
- electrical response in validated envelope;
- thermal response consistent with healthy characterization.

---

## 23.2 ELECTRICAL_RESPONSE_MISSING

Requires:

- valid ON command/applied state;
- branch electrical response absent/outside expected active envelope.

---

## 23.3 THERMAL_EFFECTIVENESS_DEGRADED

Requires:

- electrical response plausibly healthy;
- thermal response materially weaker than matched healthy baseline.

This state identifies an **effectiveness problem**.

It does not identify the component cause.

---

## 23.4 CONTROL_ELECTRICAL_ANOMALY

Examples:

```text
current while state should be OFF
wrong direction behavior
unexpected sustained branch power
```

---

## 23.5 UNKNOWN

Used when evidence is insufficient or conflicting.

`UNKNOWN` is preferable to invented certainty.

---

# 24. Legal actuation states

## 24.1 OFF

Default safe state.

---

## 24.2 ON / FULL allowed operating point

P0 baseline may use a characterized full/allowed cooling action.

“Full” means the highest operating state approved by commissioning, not automatically hardware absolute maximum.

---

## 24.3 PWM_DUTY

Conditional.

A duty is legal only if:

- IBT-2 compatibility proven;
- control waveform verified;
- thermal behavior characterized enough;
- PZEM semantics for the intended metric understood.

---

## 24.4 REVERSE

Not legal in normal P0.

The H-bridge capability does not make heating a project requirement.

---

# 25. Safety invariants

## PHY-SAFE-001 — Default off

```text
boot/reset/uninitialized control
⇒
TEC OFF
```

---

## PHY-SAFE-002 — Fan dependency

```text
TEC allowed ON
⇒
V1 hot-side fan available
```

---

## PHY-SAFE-003 — Fused cooling branch

No normal powered TEC operation without the selected branch fuse.

---

## PHY-SAFE-004 — Correct conductor class

Primary TEC current does not flow through jumper/PCT218 signal path.

---

## PHY-SAFE-005 — Logic converter boundary

XL4015 does not power the TEC.

---

## PHY-SAFE-006 — No unsafe fault injection

Fault scenarios must not deliberately:

- short supply;
- bypass fuse;
- stall fan until destructive overheating;
- expose mains;
- force known overcurrent.

---

## PHY-SAFE-007 — Condensation separation

Electronics/power terminals stay outside the intended condensation-prone chamber zone.

---

## PHY-SAFE-008 — No actuation from invalid state

Predictive actuation cannot proceed when required physical state is invalid/stale.

Local emergency/fallback semantics are separately defined.

---

## PHY-SAFE-009 — Hot-side abnormality stops escalation

If characterization indicates unsafe hot-side/module behavior, higher duty is not attempted merely to reach a target temperature.

---

## PHY-SAFE-010 — Direction is frozen

Normal operation uses one verified cooling polarity.

---

# 26. Cross-subsystem invariants

## PHY-X-001 — Sensor identity coherence

```text
logical T1/T2/T3
↔
frozen ROM IDs
↔
frozen physical positions
```

---

## PHY-X-002 — Configuration provenance

Every evidence-grade record belongs to a known:

```text
hardware_config_id
```

---

## PHY-X-003 — Shunt configuration coherence

```text
physical shunt = 50 A / 75 mV
⇒
PZEM current-range configuration = 50 A profile
```

---

## PHY-X-004 — Command/electrical separation

`command ON` never counts as electrical proof.

---

## PHY-X-005 — Electrical/thermal separation

`current present` never counts as proof of useful cooling.

---

## PHY-X-006 — Thermal effect cannot prove exact fault cause

Weak thermal response cannot be mapped directly to one failed component without additional evidence.

---

## PHY-X-007 — No hidden hardware mutation

Physical configuration changes require versioning before mixed-dataset use.

---

## PHY-X-008 — Safe-local physical authority

During backend loss, the edge device retains authority for the defined local protective action.

---

## PHY-X-009 — Prediction is advisory to policy

Model output never directly controls IBT-2.

---

## PHY-X-010 — Energy boundary coherence

PZEM energy is cooling-branch energy only.

---

# 27. Liveness obligations

## PHY-LIVE-001 — Sensor recovery

If a transient bus error clears, valid sensor acquisition should resume without requiring a false logical remap.

---

## PHY-LIVE-002 — PZEM communication recovery

After transient Modbus failure, communication may retry/recover without changing the configured 50 A range silently.

---

## PHY-LIVE-003 — Safe-local continuation

If cloud connectivity is lost while local thermal sensing remains valid, minimum local protection continues.

---

## PHY-LIVE-004 — Resynchronization

After network/backend recovery, current device state eventually becomes visible upstream.

Stale old desired commands must not be replayed as current control without validity checks.

---

## PHY-LIVE-005 — Experiment visibility

A run that cannot reach valid completion becomes explicit:

```text
INVALID / ABORTED
```

not silently merged into valid data.

---

# 28. Physical failure taxonomy

## F-PHY-01 — Sensor missing

One or more expected sensor identities unavailable.

---

## F-PHY-02 — Sensor invalid/CRC/read error

Physical channel exists but reading is not trustworthy.

---

## F-PHY-03 — Sensor position/configuration drift

Probe moved or geometry changed.

---

## F-PHY-04 — Door signal unavailable

Disturbance context missing.

---

## F-ELEC-01 — PZEM communication unavailable

Electrical observation absent.

---

## F-ELEC-02 — Wrong PZEM range/profile

Measurements semantically invalid.

---

## F-ELEC-03 — Unexpected OFF current

Potential control/electrical anomaly.

---

## F-ELEC-04 — ON current missing

Actuation/electrical-response failure candidate.

---

## F-ELEC-05 — Supply/terminal abnormality

Voltage drop, hot connector, fuse/terminal issue.

---

## F-THERM-01 — Weak cooling

Electrical response present but thermal response degraded.

---

## F-THERM-02 — Hot-side rejection limitation

Cooling degrades as hot side becomes unable to reject heat adequately.

---

## F-THERM-03 — Excessive spatial gradient

Potential airflow/geometry repeatability issue.

---

## F-NET-01 — backend/broker unavailable

Handled by SAFE_LOCAL.

---

## F-AI-01 — inference unavailable/invalid

Fallback to deterministic policy.

---

# 29. Calibration contract

## 29.1 Calibration IDs

Calibration artifacts must be versioned.

Concept:

```text
calibration_id
```

may refer to a bundle:

- DS18B20 cross-check;
- BME check;
- PZEM reference check;
- date;
- environment;
- procedure.

---

## 29.2 DS18B20 calibration/cross-check

Minimum project procedure should compare all three probes under a common stable condition.

Purpose:

- identify gross offset;
- identify bad probe;
- quantify relative disagreement.

If no traceable thermometer/reference is available:

> call it an **inter-sensor consistency check**, not certified calibration.

---

## 29.3 BME280 calibration claim

Without a proper humidity reference:

- use manufacturer accuracy as datasheet context;
- perform plausibility/stability check;
- do not claim project-measured RH accuracy.

---

## 29.4 PZEM calibration claim

Without an independent trusted meter/shunt reference:

- verify plausibility;
- verify zero/off;
- verify monotonic response;
- document limitation.

With a suitable reference:

- compare several operating points;
- estimate bias/error.

---

## 29.5 Calibration drift

Re-check after:

- significant mechanical reassembly;
- wiring change;
- sensor replacement;
- unexplained dataset shift.

---

# 30. Characterization contract

## 30.1 Purpose

Characterization determines the **actual operating envelope** of the purchased system.

---

## 30.2 TEC characterization

At increasing allowed operating points record:

- branch V;
- branch I;
- branch P;
- T1/T2/T3;
- relevant surface/assembly observations if safely available;
- time;
- anomalies.

---

## 30.3 IBT-2 characterization

Observe:

- 3.3 V logic compatibility;
- default OFF;
- stable enable/PWM;
- heating;
- connector behavior.

---

## 30.4 V1 characterization

Evaluate:

- ability to reject heat;
- cool-down;
- sustained behavior;
- repeatability.

---

## 30.5 Chamber characterization

Derive:

- cool-down curve;
- passive warm-up;
- door disturbance response;
- recovery;
- gradient;
- run-to-run variance;
- approximate response time.

---

## 30.6 PZEM PWM characterization

If PWM will be used quantitatively:

compare:

```text
duty
vs
reported average I/P
vs
expected/reference behavior
```

Do not assume linearity.

---

# 31. Commissioning gates

Detailed evidence IDs belong to Doc 03.

The physical sequence is frozen conceptually here.

## Gate H0 — Mechanical assembly

No TEC power.

Required:

- V1 installed;
- TEC mechanically integrated;
- thermal paste applied;
- fan mounted;
- penetration sealed;
- sensor positions fixed;
- electronics panel outside chamber.

---

## Gate H1 — Sensor subsystem

ESP32 by development/USB power only.

Required:

- exactly three expected DS18B20 ROM IDs;
- BME read;
- MC-38 open/close verified.

No TEC power.

---

## Gate H2 — Logic power

- XL4015 adjusted/verified around intended 5 V rail;
- logic modules powered;
- no TEC actuation.

---

## Gate H3 — PZEM / RS-485

Required:

- communication-side power;
- MAX3485 at correct rail;
- A/B verified;
- Modbus response;
- 50 A profile verified;
- V/I/P/Wh readable.

---

## Gate H4 — IBT-2 logic

Before meaningful TEC load:

- default OFF;
- enable behavior;
- direction behavior;
- reset behavior;
- 3.3 V logic compatibility.

---

## Gate H5 — Power branch

Required:

- fuse installed;
- high-current wiring;
- shunt;
- terminal check;
- V1 fan operating.

---

## Gate H6 — Low-power / conservative TEC test

Start at a conservative validated approach.

Required:

- current present;
- correct cooling face;
- hot side rejects heat;
- no abnormal connector/wire/module behavior.

---

## Gate H7 — Full characterization

Increase only within the safe characterized envelope.

Collect:

- V/I/P;
- actuation state;
- T1/T2/T3;
- BME;
- door;
- timing;
- observed thermal response.

---

## Gate H8 — Closed-loop physical verification

Required:

```text
backend/command path
→ edge apply
→ electrical response
→ thermal response
→ verify
```

Predictive actuation cannot precede H8 baseline verification.

---

# 32. Experiment physical-configuration invariants

## EXP-PHY-001 — Fixed sensor positions

Final campaign uses the same mounting positions within a comparison block.

---

## EXP-PHY-002 — Fixed chamber assembly

Do not repeatedly disassemble V1/TEC between paired runs unless re-characterized.

---

## EXP-PHY-003 — Initial-condition rule

Each scenario defines an acceptable initial thermal band.

A run starting outside the band is flagged before analysis.

---

## EXP-PHY-004 — Reset/recovery rule

Runs require a predeclared reset/settling criterion.

Do not start the next run merely because enough clock time passed if state is not comparable.

---

## EXP-PHY-005 — Disturbance repeatability

Door scenario specifies:

- open timing;
- open duration;
- closure condition;
- what counts as failed execution.

---

## EXP-PHY-006 — Controller comparability

Reactive/predictive pairs use the same physical hardware configuration.

---

# 33. Physical data invalidation rules

A run is invalid for final physical comparison if any required condition occurs, unless the scenario specifically studies that condition:

- unknown hardware configuration;
- sensor identity mismatch;
- sensor position changed;
- multiple required thermal channels missing;
- PZEM range wrong;
- corrupted time/sequence preventing alignment;
- door protocol not executed within tolerance;
- manual intervention not recorded;
- unsafe shutdown;
- uncontrolled hardware reassembly;
- data capture gap overlapping the primary outcome.

Doc 03 freezes exact tolerances.

---

# 34. PWM correctness contract

## 34.1 PWM is not slow bang-bang

A sequence such as:

```text
3 s ON
3 s OFF
```

must not be called high-frequency PWM.

It is duty-cycled time-proportioning.

---

## 34.2 Candidate switching range

The old hardware integration plan proposed a low-kHz baseline such as:

```text
1–3 kHz
```

while BTS7960 silicon supports switching up to approximately 25 kHz.

This candidate range is not frozen until the purchased IBT-2 and measurement path are characterized.

---

## 34.3 Core research does not require PWM optimization

Controller A/B can be scientifically compared using the same characterized action state.

This avoids confounding:

```text
prediction timing
```

with:

```text
different actuation magnitude
```

---

# 35. Energy correctness contract

## 35.1 Instantaneous sampled power

Use:

```text
cooling_power_W
```

from validated PZEM measurements.

---

## 35.2 Run energy from sampled power

For short experiments:

\[
E_{Wh}\approx\frac{1}{3600}\sum_i P_i\Delta t_i
\]

with \(P\) in W and \(\Delta t\) in seconds.

---

## 35.3 PZEM energy counter

Use as:

- cross-check;
- longer-run measurement.

Its 1 Wh resolution can be coarse for short tests.

---

## 35.4 No whole-system efficiency claim

Without measuring all auxiliary loads:

```text
cooling-branch energy
```

is not:

```text
whole-system energy
```

and cannot directly establish whole-system COP.

---

# 36. Thermoelectric efficiency/heat-balance limits

The project may use thermoelectric equations for interpretation:

\[
Q_h=Q_c+P_{in}
\]

\[
COP=\frac{Q_c}{P_{in}}
\]

However ColdGuard does not directly measure \(Q_c\) accurately enough in P0 to claim a rigorous TEC COP.

Therefore:

### PHY-THERMO-001

Do not calculate “COP” from:

```text
temperature drop / electrical power
```

and label it thermodynamic COP.

A proper \(Q_c\) estimate requires a valid thermal-load model or calorimetry.

---

# 37. Sensor-fusion correctness

## 37.1 No majority vote assumption

Three DS18B20 sensors are spatial sensors.

They are not three redundant sensors at the same point.

Therefore:

```text
median(T1,T2,T3)
```

is not automatically “the true chamber temperature.”

---

## 37.2 Tmax as conservative signal

`Tmax` may be useful for protection because it represents the warmest observed location.

If used as control truth, that policy choice must be explicit.

---

## 37.3 Tmean as state feature

`Tmean` is useful as a summary but can hide gradients.

Store raw channels.

---

# 38. Physical authority matrix

| Question | Correct authority |
|---|---|
| Which probe is T1? | frozen ROM↔position map |
| Is door open? | MC-38 semantic state |
| Did backend ask for cooling? | command record |
| Did device accept/apply it? | edge applied state |
| Did branch draw current? | PZEM |
| Did chamber respond thermally? | DS18B20 trajectory |
| Is PZEM current meaningful? | correct 50 A profile + validated module state |
| Is TEC current “15 A by definition”? | **No** — measured actual SKU |
| Is IBT-2 “43 A continuous”? | **No** — module characterization required |
| Is one run comparable to another? | same/controlled hardware configuration + Doc 03 protocol |
| Is a risk score a probability? | only if Doc 05B calibration contract passes |

---

# 39. Configuration objects

## 39.1 Hardware configuration

Conceptually:

```yaml
hardware_config_id: CG-HW-001

board:
  purchased: "Dual ESP32-S3R2 + W25Q32 + CH343G"
  primary_mcu: "RIGHT" # after physical verification
  pin_map_version: "pin-v1"

thermal:
  chamber: "HS2-6L"
  tec_sku: "<exact purchased SKU label>"
  thermal_assembly: "V1-12V"

sensors:
  ds18b20:
    T1: "<ROM>"
    T2: "<ROM>"
    T3: "<ROM>"
  bme280: "module-1"
  door: "MC-38"

electrical:
  pzem: "PZEM-017"
  shunt: "50A-75mV"
  pzem_range_profile: "50A"
  driver: "IBT-2"
  psu: "12V-33A"
```

Exact serialization belongs to Doc 02.

---

## 39.2 Calibration configuration

```yaml
calibration_id: CG-CAL-...
thermal_probe_check: ...
bme_check: ...
pzem_check: ...
date: ...
notes: ...
```

---

## 39.3 Operating envelope

Commissioning produces:

```yaml
operating_envelope_id: CG-OE-...
max_allowed_duty: ...
healthy_current_range: ...
healthy_power_range: ...
response_window: ...
thermal_stop_conditions: ...
```

Values are deliberately blank before measurement.

---

# 40. Legal duplicates and stale physical inputs

## 40.1 Duplicate telemetry

Two records with same:

```text
boot_id + seq
```

represent one acquisition record for idempotent storage semantics.

They do not become two independent physical samples.

---

## 40.2 Out-of-order telemetry

Historical storage may preserve an older late-arriving sample.

Current state must not regress blindly to it.

---

## 40.3 Old command

A delayed old command must not override a newer physical policy state if its validity/identity no longer applies.

---

# 41. Measurement uncertainty principles

## 41.1 Datasheet accuracy is not dataset uncertainty

DS18B20 ±0.5 °C specification does not mean:

```text
every recorded T has exactly ±0.5 °C uncertainty
```

because assembly, placement, airflow, thermal lag and calibration also matter.

---

## 41.2 Relative comparison can be stronger than absolute accuracy

For paired experiments on one frozen setup, repeatability and stable bias may matter more than certified absolute temperature.

Report this distinction honestly.

---

## 41.3 Do not over-propagate fake precision

PZEM resolution:

```text
0.01 A
```

does not prove measurement accuracy of ±0.01 A.

Resolution and accuracy are different.

---

## 41.4 Model output precision follows input/evidence quality

Do not display:

```text
risk probability = 73.4281%
```

if the model is not calibrated and input state has material uncertainty.

---

# 42. Temperature-control boundary

The prototype protects a configured **testbed thermal criterion**.

It does not establish:

- product-specific regulatory cold-chain range;
- medical cold-chain compliance;
- food-safety threshold.

The final experiment threshold must be justified as a **testbed research boundary** unless a specific commodity standard is explicitly adopted with evidence.

---

# 43. Product/commodity interpretation

If the team uses dragon fruit or another commodity as narrative context:

```text
commodity context
```

does not change sensor capability.

The current hardware observes:

- air-region temperature;
- RH context;
- door;
- cooling electrical response.

It does not observe biological quality directly.

---

# 44. Database/backend implications derived from this contract

Doc 02 implementation must preserve:

- raw T1/T2/T3 independently;
- physical sensor identity;
- hardware config;
- calibration ID;
- quality flags;
- command vs applied state;
- PZEM raw electrical fields;
- timing/sequence;
- run identity.

The backend must not collapse:

```text
desired = reported = verified
```

into one boolean.

---

# 45. AI implications derived from this contract

Person B / Doc 05B must:

- split independent runs before window generation;
- use past-only features;
- retain missing/quality semantics;
- not use future command/response information to predict a prior event;
- version features;
- avoid random-row split.

Physical invalidity upstream cannot be fixed by ML preprocessing downstream.

---

# 46. Control implications derived from this contract

Person D / Doc 02 must never implement:

```text
if model_score > x:
    write PWM pin immediately
```

The required logical path is:

```text
fresh/valid physical state
→ prediction
→ policy
→ safety gate
→ command
→ local validation
→ actuation
→ response verification
```

---

# 47. Acceptance scenarios for this contract

These are conceptual correctness scenarios.

Exact test IDs/procedures belong to Doc 03.

## ACC-PHY-01 — Sensor identity survives reboot

Setup:

- freeze T1/T2/T3 ROM map;
- reboot device.

Assert:

- same logical mapping;
- no position swap.

---

## ACC-PHY-02 — Door polarity

Open/close physical chamber.

Assert semantic state matches physical state.

---

## ACC-PHY-03 — PZEM 50 A profile

Read configuration.

Assert:

```text
current range = 50 A
```

before final measurement acceptance.

---

## ACC-PHY-04 — Default OFF

Reset/boot with power branch ready.

Assert:

- no unintended branch energization.

---

## ACC-PHY-05 — Cooling direction

Low-power/conservative first actuation.

Assert:

- intended cold side cools;
- hot side heats/rejects;
- polarity frozen.

---

## ACC-PHY-06 — Command is not proof

Issue ON while intentionally preventing legal execution in a safe test mode.

Assert:

- command recorded;
- no electrical response;
- health != HEALTHY_RESPONSE.

---

## ACC-PHY-07 — Electrical without thermal effectiveness

Use a safe controlled degradation method only if approved.

Assert:

- electrical response remains plausible;
- thermal response weak;
- diagnosis = effectiveness degraded/unknown, not invented root cause.

---

## ACC-PHY-08 — PZEM PWM caution

At several validated duties:

- record PZEM;
- compare expected trend/reference;
- determine whether power is usable quantitatively.

---

## ACC-PHY-09 — Sensor missing

Disable/disconnect one sensor safely.

Assert:

- explicit degraded state;
- no silent remap.

---

## ACC-PHY-10 — Network loss

Disconnect broker/backend.

Assert:

- local thermal sensing remains;
- SAFE_LOCAL maintains allowed protective behavior.

---

# 48. Proof obligations for Doc 03

Doc 03 must provide evidence for at least:

| Contract | Proof family |
|---|---|
| DS18B20 identity | discovery/reboot test |
| sensor position freeze | photo/fixture + config |
| PZEM range | config/readback evidence |
| electrical plausibility | multi-point load cross-check |
| default OFF | boot/reset powered test |
| cooling direction | low-power thermal test |
| healthy cooling envelope | characterization runs |
| response delay | step-response data |
| door disturbance | repeated controlled runs |
| hardware repeatability | repeated baseline runs |
| SAFE_LOCAL | connectivity-loss run |
| PZEM PWM semantics | characterization if PWM metric used |
| final fuse choice | measured-current/thermal rationale |
| final GPIO map | actual board bring-up evidence |

No AI experiment gate may waive missing critical physical proof.

---

# 49. What this correctness contract intentionally does not solve

This document does not define:

- MQTT QoS;
- retain semantics;
- topic ACL;
- database migrations;
- REST endpoints;
- dashboard UI;
- XGBoost hyperparameters;
- final risk threshold;
- number of experimental repetitions;
- statistical test selection;
- Git workflow;
- weekly work ownership.

Those belong downstream.

---

# 50. Implementation guidance derived from the contract

Recommended firmware modules should make boundaries visible:

```text
Sensors/
  Ds18b20Manager
  Bme280Reader
  DoorSensor

Electrical/
  Pzem017Client
  Rs485Transport

Actuation/
  CoolingDriver
  AppliedState

Safety/
  PhysicalInterlocks
  SafeLocal

Telemetry/
  SnapshotBuilder
  QualityFlags

Config/
  HardwareConfig
  CalibrationConfig
  PinMap
```

Exact folder names are not normative.

Responsibilities are.

---

# 51. Report-ready theory summary

ColdGuard's physical-correctness model can be summarized as:

```text
PHYSICAL CORRECTNESS
=
known configuration
+ stable sensor identity
+ valid measurement semantics
+ safe electrical topology
+ legal actuation
+ independent electrical feedback
+ independent thermal feedback
+ explicit degraded/unknown states
+ reproducible physical conditions
```

and:

```text
COMMAND SUCCESS
≠
PHYSICAL SUCCESS
```

Instead:

```text
physical success
requires
applied action
+ electrical response
+ thermal response
```

within a validated operating envelope.

---

# 52. Authoritative external references

## Hardware/component sources

**[R1] Analog Devices — DS18B20.**  
1-Wire, unique 64-bit ROM, multidrop, programmable resolution, temperature/accuracy specifications.  
https://www.analog.com/en/products/ds18b20.html

**[R2] Bosch Sensortec — BME280 Datasheet BST-BME280-DS001.**  
I²C/SPI, supply ranges, humidity response and accuracy.  
https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf

**[R3] Espressif — ESP32-S3 Hardware Design Guidelines.**  
ESP32-S3R2 in-package 2 MB Quad-SPI PSRAM; R8/R8V Octal PSRAM mapping.  
https://documentation.espressif.com/esp-hardware-design-guidelines/en/latest/esp32s3/index.html

**[R4] Espressif — ESP32-S3 GPIO Programming Guide.**  
GPIO restrictions, strapping pins, flash/PSRAM notes.  
https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/gpio.html

**[R5] Analog Devices — MAX3485.**  
3.3 V half-duplex RS-485/RS-422 transceiver, 10 Mbps.  
https://www.analog.com/en/products/max3485.html

**[R6] Infineon — BTS7960 Datasheet Rev. 1.1.**  
Half-bridge electrical/protection/current-limit/PWM characteristics.  
https://www.infineon.com/dgdl/BTS7960_Datasheet.pdf

**[R7] PZEM-017 RS-485/Modbus manual mirror.**  
Measurement registers, current-range profile, serial protocol and resolutions.  
https://manuals.plus/ae/32913960037

**[R8] Ferrotec — Thermoelectric Reference Guide.**  
Thermoelectric cooling, heat-sink considerations and \(Q_h=Q_c+P_{in}\).  
https://thermal.ferrotec.com/technology/thermoelectric-reference-guide/

## IoT/security sources relevant to physical correctness

**[R9] NIST IR 8259 Rev. 1 (2026).**  
Foundational cybersecurity activities for IoT product manufacturers.  
https://csrc.nist.gov/pubs/ir/8259/r1/final

**[R10] NIST IR 8259A.**  
IoT device cybersecurity capability core baseline.  
https://csrc.nist.gov/pubs/ir/8259/a/final

---

# 53. Source authority policy

When hardware sources conflict:

```text
1. exact documentation/markings shipped with the purchased unit
2. official manufacturer datasheet for exact IC/SKU
3. controlled team commissioning measurement
4. reputable module manual/distributor documentation
5. seller listing
6. forum/community report
```

Important nuance:

A team measurement does not override an official absolute maximum for an exact known IC.

But a generic IC datasheet does not automatically certify a whole third-party module.

---

# 54. Freeze checklist

## Hardware

- [ ] Doc 00 and Doc 01 BOM tables match exactly.
- [ ] No INA226 remains in P0.
- [ ] No second TEC remains in P0.
- [ ] Chamber is HS2 6 L.
- [ ] PZEM is PZEM-017.
- [ ] Shunt is 50 A / 75 mV.
- [ ] MAX3485 module is 3.3 V.
- [ ] Driver is BTS7960 / IBT-2.
- [ ] PSU is 12 V / 33 A.
- [ ] Fuse choices remain 10/15/20 A until measured selection.
- [ ] Wire classes remain frozen.

## Sensors

- [ ] T1/T2/T3 roles defined.
- [ ] ROM identity mapping required.
- [ ] BME contextual role defined.
- [ ] Door polarity must be commissioned.

## Electrical

- [ ] 50 A PZEM profile required.
- [ ] PZEM is cooling-branch measurement only.
- [ ] PZEM PWM limitations stated.
- [ ] `43 A IBT-2 continuous` claim prohibited.
- [ ] Generic TEC1-12715 electrical rating prohibited.

## Safety

- [ ] default OFF invariant.
- [ ] fan/TEC dependency.
- [ ] fuse requirement.
- [ ] no jumper TEC path.
- [ ] no unsafe fault injection.
- [ ] no silent added hardware.

## Evidence

- [ ] hardware config ID required.
- [ ] calibration ID required where applicable.
- [ ] invalid/degraded states explicit.
- [ ] command/electrical/thermal evidence separated.
- [ ] experimental physical invalidation rules defined.

---

# 55. North star

> **A ColdGuard measurement is trustworthy only when we know what physical thing produced it, where that thing was mounted, under which hardware configuration it was acquired, whether the measurement path was valid, and whether any command-derived claim is independently supported by the actual electrical and thermal response.**

> **The hardware is not a prop for the AI. The hardware defines the physical truth that every downstream IoT, AI, control and experimental claim must respect.**
