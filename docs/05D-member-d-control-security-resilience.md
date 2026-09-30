# COLDGUARD — HỆ THỐNG BẢO VỆ CHUỖI LẠNH CHỦ ĐỘNG
## Member D Execution Playbook · Control · Safety · Security · Resilience · Physical Verification

> **Document:** `docs/05D-member-d-control-security-resilience.md`  
> **Course:** Internet of Things (IoT) — Course Project / Bài tập lớn  
> **Project:** **ColdGuard — Hệ thống bảo vệ chuỗi lạnh chủ động**  
> **Role:** **Member D — Control, Security & Resilience**  
> **Planning horizon:** **24 weeks**  
> **Planned focused effort:** **279 hours**  
> **Average:** **11.6 h/week**  
> **Parents:**  
> `00-project-scope-architecture.md`  
> `01-physical-measurement-correctness-contract.md`  
> `02-aiot-closed-loop-engineering.md`  
> `03-verification-experiments-demo.md`  
> `04-team-execution-plan.md`  
> **Sibling playbooks:** `05A`, `05B`, `05C`  
> **Normative role:** chronological execution contract for Member D. This document converts the project’s control, safety, command-integrity, security and resilience responsibilities into weekly issue packs, quantitative acceptance criteria, negative tests, fault campaigns, evidence artifacts, handoffs and leader-review checkpoints.  
> **Non-authority rule:** this playbook MUST NOT redefine the exact BOM, physical measurement meaning, model-training semantics, experiment statistics or backend persistence contracts. If this file conflicts with Docs 00–04, the parent document wins.  
> **Control principle:** **AI never actuates directly.** Every predictive output is advisory input to a deterministic, versioned policy and safety gate.  
> **Safety principle:** local protection must not depend on MQTT, backend, database, frontend or XGBoost being available.  
> **Security principle:** authentication/TLS/ACL protect the command path, but they do not replace freshness, idempotency, physical-state validation or device-side safety.  
> **Primary mission:** ensure that every ColdGuard actuation is **legal, fresh, bounded, locally safe, auditable, physically verified and recoverable under network/backend/AI failure**.

> **Member D north star.**  
> **The job is not “turn the TEC on when AI says risk is high.” The job is to make it impossible for an untrusted, stale, duplicated, out-of-range or physically unsafe decision to become an uncontrolled actuation—and to prove that minimum thermal protection survives when remote intelligence disappears.**

---

# 0. How to use this playbook

Every Member D week must finish with:

```text
control/security mechanism
+
negative/failure test
+
authoritative final-state assertion
+
evidence
+
handoff
```

A control feature is not complete because:

```text
happy-path command worked once
```

It is complete only when the member can also explain:

```text
what happens if the command is stale?
duplicated?
out of range?
wrong device?
network lost?
AI unavailable?
sensor degraded?
ACK lost?
actuator draws no current?
current flows but cooling is ineffective?
```

---

# 1. Role contract

## 1.1 Member D owns

### Control semantics

- safety hierarchy;
- Controller A;
- Controller B;
- policy state machine;
- hysteresis;
- persistence;
- dwell rules when needed;
- command reason codes;
- command freshness;
- allowed action range;
- SAFE_LOCAL entry/exit.

### Command integrity

- command validation;
- TTL/expiry;
- idempotency expectation;
- duplicate semantics;
- stale-state rejection;
- out-of-range rejection;
- wrong-target rejection.

### Physical verification semantics

- electrical-response verification;
- thermal-response verification;
- command verification state;
- cooling-health interpretation;
- degraded/unknown classification.

### Security

- threat model;
- device identity requirements;
- TLS/credential baseline;
- broker ACL requirements;
- backend command authorization;
- negative security tests;
- replay/stale-command defense.

### Resilience

- broker outage;
- backend outage;
- database outage policy;
- AI unavailable behavior;
- reconnect/resynchronization;
- watchdog/liveness principles;
- fail-safe/fail-operational reasoning.

### Final safety case

- hazard/invariant matrix;
- negative-test matrix;
- residual risks;
- defense of why Controller B is bounded.

---

## 1.2 Member D does not own

D does not independently define:

```text
what T1 physically is
what current range is healthy before A measures it
which XGBoost feature set wins
which database table schema is canonical
which run is statistically valid
```

D consumes:

- A physical envelopes;
- B predictive evidence;
- C durable state/command infrastructure.

---

# 2. Safety hierarchy

ColdGuard control authority is ordered:

```text
1. physical/electrical safety
2. local deterministic protection
3. degraded/fault handling
4. Controller A reactive policy
5. Controller B predictive intervention
6. energy optimization
```

A lower layer can never override a higher one.

---

# 3. Core control states

Canonical high-level states:

```text
BOOT
SELF_TEST
NORMAL
WATCH
PREEMPTIVE_COOLING
CRITICAL_PROTECTION
FAULT
SAFE_LOCAL
FAULT_LOCKOUT
```

Implementation may compress/extend internal states.

The externally meaningful semantics must remain.

---

# 4. Controller A contract

## Purpose

- deterministic baseline;
- cloud-independent fallback basis;
- physical control reference.

## Inputs

Primarily:

```text
valid thermal state
quality
applied state
local configuration
```

## Decision family

```text
upper threshold
lower threshold
hysteresis
optional persistence/dwell
```

## Output

```text
OFF
or
frozen characterized ON/action state
```

Core Controller A/B comparison should use the same action magnitude.

---

# 5. Controller B contract

## Purpose

Use predictive warning to act earlier.

## Difference from A

Primary difference:

```text
timing of legal action
```

not arbitrary stronger cooling.

## Required path

```text
physical state
→ feature/prediction
→ policy
→ safety gate
→ command
→ device validation
→ applied state
→ electrical verify
→ thermal verify
```

No shortcut.

---

# 6. Safety gate inputs

Before remote predictive action, policy must know enough about:

```text
physical quality
thermal freshness
device mode
prediction freshness
model version
policy version
current applied state
command history
fault state
network/twin freshness
allowed operating envelope
```

---

# 7. Safety gate decision

Concept:

```text
if hard safety fault:
    reject / safe action

elif critical thermal protection:
    Controller A hard protection dominates

elif state invalid/stale:
    predictive action prohibited

elif predictive warning valid:
    preemptive action may be allowed

else:
    normal/reactive behavior
```

---

# 8. Command validation contract

Device-side validation includes:

```text
schema
device_id
command_id
expiry
allowed action
local safety
state freshness
duplicate identity
```

Backend authorization is not sufficient.

---

# 9. Command freshness

Each remote actuation command has:

```text
created_at
expires_at
```

If expired:

```text
REJECT
NO ACTUATION
```

Transport-level Message Expiry may be used as defense in depth.

Payload-level expiry remains authoritative for command semantics.

---

# 10. Idempotency

Same:

```text
command_id
```

repeated due QoS 1/network retry:

```text
must not create a second logical physical action
```

Device returns canonical result/state.

---

# 11. Command retain rule

```text
command retain = false
```

MQTT retained messages are delivered to future matching subscribers.

That is useful for state.

It is unsafe for old actuation intent.

---

# 12. Physical verification

## Electrical verification

After legal ON:

```text
PZEM current/power enters measured healthy active envelope
within measured response window
```

## Thermal verification

After electrical response:

```text
thermal trajectory demonstrates expected useful cooling response
within characterized thermal window
```

---

# 13. Verification states

```text
NOT_REQUIRED
PENDING
ELECTRICAL_VERIFIED
THERMAL_VERIFIED
VERIFIED
FAILED_ELECTRICAL
FAILED_THERMAL
UNKNOWN
```

---

# 14. Cooling-health states

From Doc 01:

```text
HEALTHY_RESPONSE
ELECTRICAL_RESPONSE_MISSING
THERMAL_EFFECTIVENESS_DEGRADED
CONTROL_ELECTRICAL_ANOMALY
UNKNOWN
```

D owns decision semantics.

A supplies physical envelopes.

C stores/evidences them.

---

# 15. Failure diagnosis boundary

Allowed:

```text
electrical response missing
```

Not automatically:

```text
TEC broken
```

Allowed:

```text
thermal effectiveness degraded
```

Not automatically:

```text
thermal paste failed
```

Without sufficient evidence.

D classifies observable failure mode, not imaginary root cause.

---

# 16. SAFE_LOCAL contract

SAFE_LOCAL is a device-local deterministic mode used when the remote control/intelligence path is unavailable or untrusted.

Possible triggers:

```text
broker disconnected beyond grace
backend state unavailable
prediction pipeline unavailable
twin synchronization insufficient
remote command path not trusted
```

---

# 17. SAFE_LOCAL inputs

Must use locally available validated inputs.

At minimum:

```text
DS18B20 thermal state
local threshold config
local actuator state
physical safety state
```

---

# 18. SAFE_LOCAL policy

Concept:

```text
T >= upper
→ cooling ON

T <= lower
→ cooling OFF
```

with:

- hysteresis;
- state validity;
- safety interlocks.

No cloud dependency.

---

# 19. SAFE_LOCAL exit

Remote mode may resume only when:

```text
network stable
broker connected
backend current state synchronized
fresh telemetry present
no stale command
prediction healthy if Controller B requested
no active critical fault
```

Reconnect does not mean “immediately trust desired state”.

---

# 20. Device watchdog/liveness principle

ESP-IDF provides:

- Interrupt Watchdog Timer;
- Task Watchdog Timer.

TWDT is intended to detect tasks that run too long without yielding.

Member D should ensure local safety/control execution is not indefinitely starved by:

- MQTT reconnect loops;
- Modbus retry loops;
- blocking backend waits.

Exact watchdog timeout is implementation-derived.

Do not choose a timeout that conflicts with legitimate long operations.

---

# 21. Security objectives

ColdGuard security baseline aims for:

```text
device identity
command-source authorization
encrypted transport
least privilege
freshness
idempotency
audit
safe degradation
```

Not:

```text
formal certification
penetration-test completeness
production zero-trust architecture
```

---

# 22. NIST IoT baseline interpretation

NIST IR 8259A defines a core baseline of device cybersecurity capabilities.

NIST IR 8259 Rev.1 (2026) updates foundational cybersecurity activities for IoT products.

ColdGuard uses this as a design lens for:

- identification;
- configuration;
- data protection;
- logical access;
- update/maintenance thinking;
- cybersecurity state awareness.

The coursework project does not claim NIST compliance certification.

---

# 23. Threat model actors

At minimum consider:

```text
unauthorized local network client
stale legitimate command
duplicated legitimate command
misconfigured backend user
compromised/incorrect frontend path
network partition
broker restart
backend restart
database outage
AI/model failure
sensor failure
device task stall
```

---

# 24. Threats and mitigations

| Threat | Mitigation |
|---|---|
| forged command | auth + ACL + backend authorization + device validation |
| stale command | TTL/expiry |
| duplicate command | command ID/idempotency |
| replay after reconnect | expiry + command identity + reconciliation |
| wrong-device command | device target validation |
| out-of-range action | device/policy range gate |
| frontend bypass | no direct unrestricted broker publish |
| broker loss | SAFE_LOCAL |
| AI loss | Controller A/SAFE_LOCAL |
| sensor degraded | explicit degraded/fallback |
| ACK lost | reconciliation with reported/physical state |
| current absent after ON | electrical verification failure |
| current present while OFF | high-severity anomaly |

---

# 25. Security credential baseline

Recommended minimum:

```text
device credential
backend credential
scoped broker ACL
TLS-capable broker listener
backend authenticated command endpoint
```

No public anonymous command writer.

---

# 26. Secure Boot / Flash Encryption stance

ESP32-S3 supports security hardening features.

However:

```text
Secure Boot v2
Flash Encryption
irreversible eFuse changes
```

are **optional/hardening**, not P0.

They are opened only after core control/evidence is stable and only with a validated recovery/flashing procedure.

Do not brick the board for feature points.

---

# 27. OTA stance

OTA is not P0.

If added later:

- signed artifact;
- version;
- rollback/recovery;
- audit.

Control safety should not depend on OTA being implemented.

---

# 28. Reason-code baseline

Control/security reason codes:

```text
THRESHOLD_HIGH
THRESHOLD_RECOVERED
PREDICTED_CRITICAL
RISK_PERSISTENT
DOOR_DISTURBANCE
SENSOR_DEGRADED
AI_UNAVAILABLE
NETWORK_UNAVAILABLE
BACKEND_UNAVAILABLE
ELECTRICAL_RESPONSE_MISSING
THERMAL_EFFECTIVENESS_DEGRADED
CONTROL_ELECTRICAL_ANOMALY
COMMAND_EXPIRED
COMMAND_DUPLICATE
COMMAND_OUT_OF_RANGE
COMMAND_WRONG_DEVICE
COMMAND_SAFETY_BLOCKED
COMMAND_STATE_STALE
AUTHORIZATION_FAILED
SAFE_LOCAL_ENTER
SAFE_LOCAL_EXIT
RECOVERY_VERIFIED
RECOVERY_FAILED
```

---

# 29. Member D Definition of Done

By W24 Member D hands over:

```text
safety hierarchy
hazard/invariant matrix
Controller A
Controller B
policy versions/config
command validation matrix
reason codes
freshness/idempotency rules
physical verification semantics
cooling-health state machine
SAFE_LOCAL implementation contract
outage/reconnect behavior
threat model
broker/backend authorization requirements
security negative-test evidence
resilience campaign
final safety case
residual-risk register
defense runbook
```

---

# 30. Member D interfaces

## 30.1 A → D

A supplies:

```text
safe operating envelope
OFF current envelope
healthy active current/power
allowed actuation state
physical response windows
sensor-quality behavior
default-off evidence
```

D does not guess these.

---

## 30.2 D → A

D supplies:

```text
local policy
threshold/hysteresis config
allowed command range
expiry handling
idempotency behavior
SAFE_LOCAL transitions
fault reactions
```

---

## 30.3 B → D

B supplies:

```text
model version
feature version
risk semantics
horizon
decision threshold candidate
persistence evidence
false-warning rate
EWT
AIW
limitations
```

---

## 30.4 D → B

D supplies:

```text
policy threshold actually used
persistence/dwell
action timing
reason codes
Controller A/B identity
```

---

## 30.5 C → D

C supplies:

```text
fresh twin state
prediction record
command lifecycle
ACK
reconnect state
authn/authz infrastructure
physical verification events
```

---

## 30.6 D → C

D supplies:

```text
policy_version
controller state
TTL/freshness rules
reason codes
verification states
security authorization requirements
SAFE_LOCAL/recovery state events
```

---

# 31. Personal risk register

| Risk | Member D response |
|---|---|
| predictive output bypasses safety | one policy gate only |
| threshold chatter | hysteresis/persistence |
| stale command after reconnect | TTL + non-retained + reconciliation |
| QoS duplicate causes repeated actuation | command ID/idempotency |
| network loss stops control | SAFE_LOCAL |
| model unavailable | Controller A fallback |
| PZEM unavailable | degrade verification, preserve thermal safety |
| sensor invalid | prohibit predictive action |
| ACK confused with success | physical verification state |
| high current while OFF | severe anomaly/fault handling |
| weak cooling misdiagnosed | classify effectiveness, not root cause |
| backend DB down but command continues | remote predictive commands disabled |
| ACL too broad | least privilege negative test |
| test injection unsafe | software/network/low-voltage faults first |
| watchdog reset causes unsafe output | boot default-off + state recovery |
| Controller B tuned during final A/B | W16/W18 freeze governance |
| security feature bricks board | hardening remains optional |

---

# 32. Evidence convention

Recommended:

```text
evidence/D/Wxx/
```

Each evidence README includes:

```text
goal
policy version
hardware config
model version if relevant
test ID
setup
input state
expected action
observed action
final state
pass/fail
reason
limitations
```

---

# 33. Week 01 — Safety hierarchy, hazard ledger and trust-boundary map
**Effort:** **10 h**  
**Parent:** `04 W01`

## Objective

Define what may never happen before control code exists.

---

## D-W01-01 — Safety hierarchy review

Translate Docs 00–03 into a one-page authority chain:

```text
physical safety
→ local protection
→ reactive
→ predictive
→ optimization
```

---

## D-W01-02 — Hazard ledger

At minimum:

- unintended boot actuation;
- fan unavailable with TEC ON;
- stale command;
- duplicate command;
- wrong-device command;
- out-of-range duty;
- invalid sensor-driven actuation;
- current while commanded OFF;
- hot-side abnormality;
- cloud loss;
- control task starvation.

---

## D-W01-03 — Trust-boundary diagram

Mark:

```text
device
broker
backend
database
frontend
model
operator
```

and what each can/cannot authorize.

---

## D-W01-04 — P0 security boundary

Freeze:

```text
identity
TLS-capable broker
ACL
backend authz
TTL
idempotency
audit
```

Optional:

```text
Secure Boot
Flash Encryption
OTA
```

---

## Deliverables

```text
safety-hierarchy.md
hazard-ledger-v0.md
trust-boundary.png
security-baseline-v0.md
```

---

## Pass criteria

No path exists conceptually where:

```text
model
→ GPIO
```

directly.

---

# 34. Week 02 — Policy-state skeleton and SAFE_LOCAL design
**Effort:** **11 h**  
**Parent:** `04 W02`

## Objective

Define deterministic states before integrating prediction.

---

## D-W02-01 — Policy state machine

Specify:

```text
NORMAL
WATCH
PREEMPTIVE_COOLING
CRITICAL_PROTECTION
FAULT
SAFE_LOCAL
FAULT_LOCKOUT
```

---

## D-W02-02 — Transition table

For every transition record:

```text
source
condition
destination
action
reason code
```

---

## D-W02-03 — SAFE_LOCAL entry

Candidate triggers:

```text
remote path unavailable
backend unhealthy
broker unavailable
AI unavailable where predictive required
state sync invalid
```

---

## D-W02-04 — SAFE_LOCAL exit

Require fresh reconciled state.

---

## D-W02-05 — Command validator contract

Draft required checks.

---

## Handoff

A receives local state/command requirements.

C receives policy-state fields.

---

# 35. Week 03 — Policy unit skeleton, command matrix and failure taxonomy
**Effort:** **11 h**  
**Parent:** `04 W03`

## Objective

Make control decisions deterministic and testable independently of hardware.

---

## D-W03-01 — Pure policy function

Concept:

```text
PolicyInput
→ PolicyDecision
```

No MQTT/DB/GPIO inside core logic.

---

## D-W03-02 — Command decision matrix

Test cases:

```text
fresh valid ON
expired
duplicate
wrong device
out of range
invalid state
safety fault
```

---

## D-W03-03 — Failure taxonomy

Map Doc 01 failures to:

```text
ignore?
degrade?
fallback?
lockout?
```

---

## D-W03-04 — Priority assertions

Unit tests prove:

```text
CRITICAL_PROTECTION > PREEMPTIVE
FAULT > optimization
```

---

# 36. Week 04 — Command v0 and actuator safety review
**Effort:** **12 h**  
**Parent:** `04 W04`

## Objective

Freeze legal remote actuation semantics around A’s first physical TEC tests.

---

## D-W04-01 — Legal actions

Initial legal family:

```text
OFF
core characterized ON
```

PWM remains conditional.

---

## D-W04-02 — Device-side safety checklist

With A:

- boot default OFF;
- reset OFF;
- opposite H-bridge direction inactive;
- enable semantics;
- allowed range;
- fan dependency.

---

## D-W04-03 — TTL semantics

Define candidate command-validity policy.

Do not choose long TTL from convenience.

Final value will use latency/plant evidence.

---

## D-W04-04 — Command/ACK reason codes v0

---

## D-W04-05 — Physical first-actuation review

Observe A’s H6 evidence.

No predictive control.

---

## Gate contribution

G1 requires D safety signoff on first legal physical actuation path.

---

# 37. Week 05 — Physical-quality integration and stale-state prevention
**Effort:** **11 h**  
**Parent:** `04 W05`

## Objective

Ensure policy consumes quality/freshness, not bare numbers.

---

## D-W05-01 — Policy input type

Include:

```text
thermal quality
electrical quality
door quality
data age
device mode
applied action
```

---

## D-W05-02 — Stale-state tests

Examples:

```text
thermal value 20 s old
latest seq missing
unknown boot
```

Predictive action must be blocked according to configured freshness.

---

## D-W05-03 — Missing-channel behavior

Review:

- one DS18B20 missing;
- BME missing;
- PZEM missing.

Distinguish:

```text
thermal safety
prediction availability
physical verification confidence
```

---

## D-W05-04 — UNKNOWN semantics

Never map unknown to healthy automatically.

---

# 38. Week 06 — Command negative tests and lifecycle integration
**Effort:** **11 h**  
**Parent:** `04 W06`

## Objective

Prove transport retry/stale inputs do not produce unsafe physical behavior.

---

## D-W06-01 — Expired command

Send expired command.

Expected:

```text
REJECTED
no actuation
```

---

## D-W06-02 — Duplicate command

Same command ID twice.

Expected:

```text
one logical application
canonical ACK
```

---

## D-W06-03 — Wrong-device

Expected:

```text
reject
```

---

## D-W06-04 — Out-of-range

Expected:

```text
reject
```

---

## D-W06-05 — Invalid-state command

Physical state stale/invalid.

Expected:

```text
SAFETY_BLOCKED / INVALID_STATE
```

---

## D-W06-06 — ACK interpretation

Verify backend UI/log never equates accepted ACK with verified cooling.

---

# 39. Week 07 — Controller A implementation
**Effort:** **12 h**  
**Parent:** `04 W07`

## Objective

Implement the deterministic controller used as baseline and fallback.

---

## D-W07-01 — Threshold source

Use A’s characterized thermal state.

Do not claim commodity-regulatory threshold unless project explicitly adopts one.

---

## D-W07-02 — Hysteresis

Freeze candidate:

```text
upper
lower
```

based on plant response/pilot.

---

## D-W07-03 — Persistence

If noisy threshold behavior exists:

```text
condition must persist for N samples/time
```

Choose from real data.

---

## D-W07-04 — Minimum dwell

Only if physical switching/chatter evidence requires it.

---

## D-W07-05 — Controller A tests

Synthetic/replay:

- warm rising;
- cooling recovery;
- noise around threshold;
- invalid sensor;
- reset.

---

## D-W07-06 — First real Controller A run

With A.

---

# 40. Week 08 — SAFE_LOCAL real integration and Gate G2
**Effort:** **12 h**  
**Parent:** `04 W08`

## Objective

Prove local protection survives remote-system loss.

---

## D-W08-01 — Broker disconnect detection

Define grace/trigger semantics.

---

## D-W08-02 — SAFE_LOCAL real test

With A/C:

```text
normal online
→ remove broker/backend path
→ local control continues
```

---

## D-W08-03 — Local-state-only proof

Verify SAFE_LOCAL does not require:

```text
database
prediction
frontend
```

---

## D-W08-04 — Reconnect preliminary

Ensure reconnect does not immediately apply stale desired.

---

## D-W08-05 — G2 control report

Required:

```text
Controller A stable
SAFE_LOCAL works
remote loss does not remove minimum protection
```

---

# 41. Week 09 — Healthy cooling-response semantics
**Effort:** **12 h**  
**Parent:** `04 W09`

## Objective

Convert A’s characterization into explicit verification/diagnosis policy.

---

## D-W09-01 — OFF envelope

Import A’s measured OFF electrical envelope.

---

## D-W09-02 — Healthy ON envelope

Import:

- current range;
- power range;
- response timing.

---

## D-W09-03 — HEALTHY_RESPONSE logic

Requires:

```text
valid ON
+ expected electrical
+ expected thermal
```

---

## D-W09-04 — UNKNOWN logic

Insufficient evidence → UNKNOWN.

---

## D-W09-05 — Verification timer

Design:

```text
command
→ wait electrical window
→ wait thermal window
→ terminal verification
```

No arbitrary instant verdict.

---

# 42. Week 10 — Safe fault-injection protocol and diagnosis design
**Effort:** **12 h**  
**Parent:** `04 W10`

## Objective

Define fault tests that prove mechanism without damaging hardware.

---

## D-W10-01 — S4 electrical-response-missing fault

Preferred:

```text
software/test mode prevents actuation
```

while command path remains visible.

---

## D-W10-02 — Sensor degraded protocol

Low-voltage/safe disconnect.

---

## D-W10-03 — PZEM unavailable protocol

Communication-layer removal.

---

## D-W10-04 — Unsafe injections blacklist

Explicitly forbid:

- short circuit;
- fuse bypass;
- destructive thermal overload;
- unsafe mains work;
- intentional long hot-side fan stall.

---

## D-W10-05 — Fault oracle table

For each fault:

```text
expected state
expected policy
expected event
expected physical effect
```

---

# 43. Week 11 — Cooling-health integration
**Effort:** **12 h**  
**Parent:** `04 W11`

## Objective

Implement diagnosis states using A’s safe fault evidence.

---

## D-W11-01 — Electrical response missing

If:

```text
ON accepted/applied
but current absent
```

classify:

```text
ELECTRICAL_RESPONSE_MISSING
```

---

## D-W11-02 — Thermal effectiveness degraded

Only if:

```text
electrical normal
thermal response weak
```

and evidence protocol supports it.

---

## D-W11-03 — Unexpected current while OFF

High severity:

```text
CONTROL_ELECTRICAL_ANOMALY
```

No need to physically force an unsafe case if backend/policy logic can be regression-tested safely.

---

## D-W11-04 — Incident actions

Define whether each state:

- warns;
- blocks predictive;
- forces OFF;
- uses local threshold;
- enters lockout.

---

## D-W11-05 — Integration with C

Persist state/reason/evidence window.

---

# 44. Week 12 — Controller A benchmark and Gate G3 control readiness
**Effort:** **12 h**  
**Parent:** `04 W12`

## Objective

Freeze the reactive baseline and show command→physical verification works.

---

## D-W12-01 — Controller A configuration v1

Freeze:

```text
threshold
hysteresis
persistence
action state
```

---

## D-W12-02 — Replay benchmark

Use B/A runs.

---

## D-W12-03 — Real benchmark

Several valid S2 runs.

---

## D-W12-04 — Command lifecycle proof

At least:

```text
reactive decision
→ command
→ ACK
→ electrical
→ thermal
→ VERIFIED
```

---

## D-W12-05 — Gate G3 signoff

No predictive control work skips this gate.

---

# 45. Week 13 — Predictive-policy semantics and latency budget
**Effort:** **12 h**  
**Parent:** `04 W13`

## Objective

Design Controller B using measured physical/system timing.

---

## D-W13-01 — AIW inputs

Consume:

- B EWT/horizon;
- A physical response delay;
- C system latency.

---

## D-W13-02 — WATCH semantics

Define:

```text
risk elevated
but not yet act
```

if useful.

---

## D-W13-03 — PREEMPTIVE semantics

Candidate:

```text
risk above threshold
for persistence
and AIW/safety valid
```

---

## D-W13-04 — Hard protection dominance

If thermal reactive threshold reached:

```text
CRITICAL_PROTECTION
```

takes precedence regardless of model.

---

## D-W13-05 — Policy config versioning

No magic constants hidden in code.

---

# 46. Week 14 — Predictive threshold/persistence and AIW gate
**Effort:** **12 h**  
**Parent:** `04 W14`

## Objective

Turn B’s model evidence into a bounded policy, not a direct actuator trigger.

---

## D-W14-01 — Receive B recommendation

Inputs:

```text
risk threshold candidate
false warning behavior
EWT
calibration status
```

---

## D-W14-02 — Persistence choice

Choose with B based on:

- score noise;
- warning duration;
- plant response.

---

## D-W14-03 — AIW gate

If:

```text
warning too late relative to measured response
```

Controller B intervention value is limited.

Do not ignore negative AIW.

---

## D-W14-04 — Probability wording

Policy may use:

```text
score threshold
```

even if not calibrated.

Do not label it probability in reason/UI unless B approved.

---

## D-W14-05 — Controller B candidate config

Versioned.

---

# 47. Week 15 — Security enforcement with C
**Effort:** **12 h**  
**Parent:** `04 W15`

## Objective

Make unauthorized command publication difficult and detectable.

---

## D-W15-01 — Broker ACL requirements

Device:

```text
publish own telemetry/event/state/ack/health
subscribe own command
```

Backend command principal:

```text
publish authorized command topic
```

---

## D-W15-02 — Backend authorization

Roles:

```text
VIEWER
OPERATOR
EXPERIMENTER
ADMIN
```

At minimum command ability is separated from read-only.

---

## D-W15-03 — Unauthorized broker test

Use test credential.

Attempt command publish.

Expected:

```text
DENIED
no device actuation
```

---

## D-W15-04 — Wrong backend role

Attempt manual command from insufficient role.

Expected:

```text
DENIED
```

---

## D-W15-05 — Credential/secret review

No secret in repository/log.

---

## D-W15-06 — TLS test plan

Define trusted/invalid endpoint test appropriate to lab.

---

# 48. Week 16 — Resilience gate: AI/network/backend/DB failure
**Effort:** **12 h**  
**Parent:** `04 W16`

## Objective

Close resilience readiness before Controller B is allowed to actuate.

---

## D-W16-01 — AI unavailable

Disable/fail inference.

Expected:

```text
no stale score reuse
Controller B unavailable
Controller A / SAFE_LOCAL continues
```

---

## D-W16-02 — Broker unavailable

Expected:

```text
SAFE_LOCAL
```

---

## D-W16-03 — Backend unavailable

Device local protection remains.

---

## D-W16-04 — DB unavailable

Policy with C:

```text
do not create new remote predictive command requiring durable audit
```

---

## D-W16-05 — Reconnect

Verify:

- old command not replayed;
- current state resynced;
- safe mode exit conditions.

---

## D-W16-06 — G4 control/security signoff

Controller B remains disabled if any core resilience test fails.

---

# 49. Week 17 — Predictive shadow mode
**Effort:** **14 h**  
**Parent:** `04 W17`

## Objective

Run full predictive policy in shadow without predictive physical action.

---

## D-W17-01 — Shadow Controller B

Consume live B prediction.

Compute:

```text
hypothetical policy transition
hypothetical action
reason
```

---

## D-W17-02 — Safety-block logging

If state invalid/stale:

record why Controller B would be blocked.

---

## D-W17-03 — Compare A vs hypothetical B timing

No physical B command.

---

## D-W17-04 — Policy determinism

Given same input:

```text
same decision
```

---

## D-W17-05 — Shadow exit report

List:

- false policy transitions;
- stale-state issues;
- unresolved ambiguity.

Only implementation bugs may be fixed without reopening B’s model result.

---

# 50. Week 18 — Controller B physical enablement
**Effort:** **14 h**  
**Parent:** `04 W18`

## Objective

Enable predictive physical intervention through the full safety chain.

---

## Preconditions

```text
G4 GREEN
A physical envelope stable
B model frozen
C command/trace stable
```

---

## D-W18-01 — Enable flag

Predictive physical actuation should have an explicit controlled enable.

---

## D-W18-02 — First predictive interventions

With A/C/B present.

---

## D-W18-03 — Complete trace

Assert:

```text
prediction
→ policy
→ safety gate
→ command
→ ACK
→ applied
→ electrical
→ thermal
```

---

## D-W18-04 — Failed verification behavior

If electrical/thermal response fails:

- do not repeatedly escalate output;
- classify;
- fall back/lock according to policy.

---

## D-W18-05 — Controller B freeze candidate

After clean dry runs:

- policy version;
- threshold;
- persistence;
- action magnitude;
- safety behavior.

---

# 51. Week 19 — Final paired A/B campaign wave 1: control integrity
**Effort:** **14 h**  
**Parent:** `04 W19`

## Objective

Protect treatment integrity during final physical experiment.

---

## D-W19-01 — Controller identity lock

Each run:

```text
A or B
```

must be exact frozen implementation.

---

## D-W19-02 — No adaptive tuning

Do not change:

- threshold;
- persistence;
- hysteresis;
- duty/action;
- failure response.

---

## D-W19-03 — Command trace review

After each run, ensure:

- expected controller issued action;
- no duplicate logical command;
- verification states sensible.

---

## D-W19-04 — Anomaly classification

If control anomaly:

- flag run;
- use Doc 03 validity rule.

Do not silently correct data.

---

## D-W19-05 — Pair integrity

Support B’s pair ledger with policy version/action evidence.

---

# 52. Week 20 — Final paired A/B campaign wave 2
**Effort:** **13 h**  
**Parent:** `04 W20`

## Objective

Complete final campaign without policy drift.

---

## D-W20-01 — Same frozen policy

No change for “better results”.

---

## D-W20-02 — Final command/verification audit

For all valid B runs:

- prediction exists;
- policy decision trace;
- command;
- ACK;
- physical verification.

For A runs:

- correct reactive trigger.

---

## D-W20-03 — Campaign anomaly report

List:

- rejected commands;
- verification failures;
- SAFE_LOCAL events;
- control anomalies.

---

## D-W20-04 — G5 control signoff

Confirm final campaign uses one frozen Controller A and one frozen Controller B policy version.

---

# 53. Week 21 — Final resilience/security campaign
**Effort:** **10 h**  
**Parent:** `04 W21`

## Objective

Run the final negative/failure matrix after primary A/B evidence is protected.

---

## D-W21-01 — Expired command

Pass:

```text
rejected
no actuation
audit event
```

---

## D-W21-02 — Duplicate command

Pass:

```text
no duplicate physical effect
```

---

## D-W21-03 — Out-of-range command

Pass:

```text
rejected
```

---

## D-W21-04 — Wrong-device command

Pass:

```text
rejected
```

---

## D-W21-05 — Unauthorized broker publish

Pass:

```text
ACL denies
```

---

## D-W21-06 — Backend authz

Insufficient role cannot actuate.

---

## D-W21-07 — Network/backend outage

SAFE_LOCAL.

---

## D-W21-08 — AI outage

Reactive/local fallback.

---

## D-W21-09 — Reconnect

No stale actuation.

---

# 54. Week 22 — Final safety case and residual-risk analysis
**Effort:** **10 h**  
**Parent:** `04 W22`

## Objective

Convert all tests into a concise defensible safety/resilience argument.

---

## D-W22-01 — Hazard→invariant→test matrix

Example:

| Hazard | Invariant | Test | Result |
|---|---|---|---|
| stale actuation | expired command rejected | SEC-* | PASS |
| duplicate actuation | idempotent command | CTRL-* | PASS |
| cloud outage | SAFE_LOCAL | RES-* | PASS |
| ACK-only false success | physical verify | CTRL-* | PASS |

---

## D-W22-02 — Residual risks

Examples:

- one physical hardware unit;
- limited fault coverage;
- no formal penetration test;
- optional secure-boot hardening absent;
- uninstrumented internal junction temperature.

---

## D-W22-03 — Severity/likelihood discussion

Keep qualitative if evidence does not justify numerical probability.

---

## D-W22-04 — Optional-scope review

Only if all core evidence is green:

- Secure Boot research;
- Flash Encryption lab plan;
- PWM energy policy.

Do not jeopardize final board.

---

# 55. Week 23 — Demo hardening and security/resilience rehearsal
**Effort:** **10 h**  
**Parent:** `04 W23`

## Objective

Make control/safety story understandable and repeatable during defense.

---

## D-W23-01 — Demo scene: verified actuation

Explain:

```text
prediction/threshold
→ policy
→ command
→ ACK
→ current
→ thermal
```

---

## D-W23-02 — Demo scene: SAFE_LOCAL

Disconnect remote path.

Show:

- mode transition;
- local protection;
- reconnect;
- no stale command.

---

## D-W23-03 — Demo scene: stale command

Prefer controlled test/replay.

Show rejection.

---

## D-W23-04 — Security explanation

Explain:

- TLS;
- ACL;
- authorization;
- TTL;
- idempotency;
- why each solves a different problem.

---

## D-W23-05 — Three full rehearsals

Measure:

- failure recovery;
- operator clarity;
- timing.

---

# 56. Week 24 — Final control/security handover
**Effort:** **8 h**  
**Parent:** `04 W24`

## Objective

No new safety/security feature.

Freeze and hand over all control evidence.

---

## D-W24-01 — Policy freeze archive

Store:

```text
Controller A config
Controller B config
policy version
reason codes
freshness
SAFE_LOCAL
```

---

## D-W24-02 — Final negative-test smoke

At least:

- expired;
- duplicate;
- unauthorized;
- SAFE_LOCAL.

No destructive test.

---

## D-W24-03 — Another member executes runbook

Member D observes.

Undocumented control assumption = defect.

---

## D-W24-04 — Final handover

Deliver:

```text
safety hierarchy
policy state machine
Controller A/B
command matrix
verification rules
SAFE_LOCAL
threat model
security config requirements
negative-test matrix
resilience evidence
residual-risk register
defense runbook
```

---

# 57. Weekly effort summary

| Week | Hours | Primary emphasis |
|---:|---:|---|
| 01 | 10 | safety/trust boundaries |
| 02 | 11 | policy/SAFE_LOCAL design |
| 03 | 11 | policy unit + command matrix |
| 04 | 12 | actuator safety / command v0 |
| 05 | 11 | quality/freshness |
| 06 | 11 | command negative tests |
| 07 | 12 | Controller A |
| 08 | 12 | SAFE_LOCAL / G2 |
| 09 | 12 | healthy verification semantics |
| 10 | 12 | safe fault protocol |
| 11 | 12 | cooling-health integration |
| 12 | 12 | Controller A / G3 |
| 13 | 12 | predictive policy / latency |
| 14 | 12 | threshold/persistence / AIW |
| 15 | 12 | ACL/authz/TLS |
| 16 | 12 | outage/resync / G4 |
| 17 | 14 | shadow Controller B |
| 18 | 14 | physical Controller B |
| 19 | 14 | final A/B wave 1 |
| 20 | 13 | final A/B wave 2 |
| 21 | 10 | resilience/security campaign |
| 22 | 10 | final safety case |
| 23 | 10 | demo hardening |
| 24 | 8 | handover |
| **Total** | **279 h** | |

---

# 58. Member D gate responsibilities

## G0

- safety hierarchy;
- trust boundaries;
- threat model.

## G1

- legal actuation path;
- boot/reset safety;
- command contract.

## G2

- Controller A;
- SAFE_LOCAL.

## G3

- physical verification;
- cooling-health semantics;
- reactive benchmark.

## G4

- predictive policy;
- AIW;
- security baseline;
- outage/reconnect.

## G5

- frozen Controller A/B integrity;
- complete verification traces.

## G6

- negative-test matrix;
- final safety case;
- reproducible resilience demo.

---

# 59. Leader review rubric for Member D

Leader should ask:

## Authority

- what can override what?
- can AI bypass local protection?

## Freshness

- how old can state/prediction/command be?
- who checks?

## Idempotency

- what happens on duplicate QoS delivery?

## Physical verification

- how do you know TEC actually worked?

## Failure

- AI down?
- broker down?
- backend down?
- DB down?
- PZEM down?
- sensor degraded?

## Security

- who can publish command?
- wrong credential?
- replay?
- stale?

## Recovery

- how does SAFE_LOCAL exit safely?

## Final experiment

- were policies frozen?
- any post-hoc tuning?

---

# 60. Common failure patterns Member D must avoid

## 60.1 AI directly writes GPIO

Forbidden.

---

## 60.2 `risk > threshold → publish command` without safety state

Incomplete.

---

## 60.3 MQTT QoS 2 as physical exactly-once

False.

Transport semantics do not guarantee application/physical side effects exactly once.

---

## 60.4 Long-lived remote command

Unsafe.

Commands expire.

---

## 60.5 Retained actuation command

Forbidden.

---

## 60.6 SAFE_LOCAL that still needs cloud threshold

Not local.

---

## 60.7 ACK means cooling success

False.

---

## 60.8 Current means useful cooling

False.

Need thermal response.

---

## 60.9 Weak cooling = TEC broken

Unsupported root-cause leap.

---

## 60.10 Fail-open predictive mode on invalid sensor

Forbidden.

Predictive action needs valid state.

---

## 60.11 Reconnect and immediately replay desired

Forbidden.

Reconcile first.

---

## 60.12 Use security features as feature-count theater

TLS/ACL/secure boot are not interchangeable.

Each solves a different threat.

---

## 60.13 Enable irreversible eFuse security at the end

High-risk unless fully rehearsed.

---

## 60.14 Tune Controller B during final A/B

Invalidates treatment freeze.

---

# 61. Controller A pseudologic

Conceptual only:

```text
if hard_fault:
    safe_fault_action

elif thermal_state invalid:
    conservative fallback / lockout per frozen policy

elif T_representative >= upper:
    ON

elif T_representative <= lower:
    OFF

else:
    hold current legal state
```

---

# 62. Controller B pseudologic

Conceptual:

```text
if hard_fault:
    safety action

elif reactive critical:
    CRITICAL_PROTECTION

elif predictive inputs invalid/stale:
    Controller A

elif risk persistent and policy permits:
    PREEMPTIVE_COOLING

else:
    Controller A / normal state
```

This illustrates authority.

Exact implementation belongs in repo.

---

# 63. Command validation pseudologic

```text
validate schema
validate device
validate expiry
check duplicate ID
check allowed action
check local safety
check state freshness

if any fail:
    reject with reason

else:
    apply
    ACK applied state
```

---

# 64. Verification pseudologic

```text
if command ON accepted:
    wait bounded electrical window

    if current not in active envelope:
        FAILED_ELECTRICAL
    else:
        ELECTRICAL_VERIFIED
        wait bounded thermal window

        if thermal response valid:
            VERIFIED
        else:
            FAILED_THERMAL / UNKNOWN
```

Do not block local control task synchronously while waiting.

Verification can be a separate state machine.

---

# 65. SAFE_LOCAL pseudologic

```text
if remote path unhealthy:
    mode = SAFE_LOCAL

while SAFE_LOCAL:
    use fresh local thermal state
    apply Controller A safety logic
    ignore stale remote intent

if remote path recovered:
    require reconciliation + fresh state
    then exit
```

---

# 66. Watchdog principle

Watchdogs help detect stalled execution.

They do not replace:

- bounded I/O timeouts;
- task architecture;
- default-off boot;
- safe persistent state.

After watchdog/reset:

```text
boot safety invariants apply again
```

No automatic restoration of stale remote ON command.

---

# 67. Security test matrix

| Test | Expected |
|---|---|
| invalid broker credential | connection/auth denied |
| unauthorized topic publish | ACL denied |
| read-only backend user commands | denied |
| expired command | device rejects |
| duplicate ID | canonical result, no duplicate effect |
| wrong device ID | rejects |
| out-of-range duty | rejects |
| malformed schema | rejects |
| stale state | predictive blocked |
| broker outage | SAFE_LOCAL |
| AI outage | Controller A/local fallback |
| reconnect with old desired | no stale actuation |

---

# 68. Resilience test matrix

| Failure | Minimum behavior |
|---|---|
| Wi-Fi/broker loss | local deterministic protection |
| backend loss | local protection |
| DB loss | no new unauditable predictive remote control |
| model failure | reactive/local fallback |
| PZEM failure | electrical verification degraded; thermal safety remains where possible |
| one DS18B20 failure | explicit degraded state |
| multiple critical thermal sensors invalid | predictive prohibited |
| task stall/reset | default-off boot + local recovery |
| ACK loss | reconcile; do not duplicate actuation |
| delayed telemetry | history stored; current state not regressed |

---

# 69. Final safety-case structure

Recommended final section:

```text
1. system boundary
2. hazards
3. safety invariants
4. security threats
5. control authority
6. negative tests
7. resilience tests
8. physical verification
9. residual risks
10. claim limitations
```

---

# 70. Residual risk principles

Do not claim zero risk.

Examples:

```text
limited physical fault coverage
single prototype
third-party modules
no formal hardware redundancy
no product certification
lab LAN threat model
optional secure-boot hardening not deployed
```

Transparent residual risk strengthens the defense.

---

# 71. NIST capability mapping example

A lightweight mapping may state:

```text
Device Identification
→ device identity / broker principal

Device Configuration
→ versioned firmware/policy/config

Data Protection
→ TLS and secret handling

Logical Access
→ broker ACL + backend roles

Software Update
→ versioned firmware; OTA optional

Cybersecurity State Awareness
→ health/events/audit/SAFE_LOCAL indicators
```

This is a project mapping.

Not a certification statement.

---

# 72. MQTT security/correctness distinction

MQTT gives:

```text
delivery/session features
```

Security layers give:

```text
identity/confidentiality/authorization
```

Application layer gives:

```text
command meaning/freshness/idempotency
```

Physical layer gives:

```text
actual effect
```

All four layers matter.

---

# 73. Final defense anchors

### Why Controller A still exists if AI is good?

> deterministic local protection is required when AI/network/backend are unavailable and acts as the experimental baseline.

### Why can’t XGBoost command directly?

> model output is uncertain and cannot enforce hardware freshness/safety/idempotency by itself.

### Why TTL?

> a previously valid command may become unsafe after delay or reconnect.

### Why idempotency?

> QoS 1 permits duplicate delivery.

### Why no retained command?

> future subscribers/reconnected devices may receive old retained state; that is unacceptable for actuation intent.

### Why ACK is not enough?

> ACK proves protocol/device handling, not electrical current or thermal effect.

### Why PZEM verification?

> independently observes electrical branch response.

### Why thermal verification after PZEM?

> current can flow while useful cooling is weak.

### Why SAFE_LOCAL?

> minimum protection must survive remote-system failure.

### Why not Secure Boot as core?

> security hardening is valuable, but irreversible configuration adds deployment risk and does not replace core command/safety correctness.

### What happens when DB is down?

> remote predictive control should not continue creating unauditable commands if durable audit is a project invariant; device falls back to local deterministic behavior.

---

# 74. Reference sources for Member D execution

**[R1] NIST IR 8259 Rev. 1 — Foundational Cybersecurity Activities for IoT Product Manufacturers (April 2026).**  
Current NIST foundational IoT cybersecurity activity guidance; supersedes the 2020 IR 8259.  
https://csrc.nist.gov/pubs/ir/8259/r1/final

**[R2] NIST IR 8259A — IoT Device Cybersecurity Capability Core Baseline.**  
Defines common device cybersecurity capability categories useful as a baseline design lens.  
https://csrc.nist.gov/pubs/ir/8259/a/final

**[R3] OASIS — MQTT Version 5.0.**  
Official QoS, retained-message, Session Expiry, Message Expiry and ACK reason-code semantics.  
https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html

**[R4] Eclipse Mosquitto — broker configuration documentation.**  
Authentication, ACL, listeners and TLS-capable broker configuration.  
https://mosquitto.org/man/mosquitto-conf-5.html

**[R5] ESP-IDF — Watchdogs for ESP32-S3.**  
Interrupt Watchdog and Task Watchdog semantics; TWDT detects tasks running for prolonged periods without yielding.  
https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/wdts.html

**[R6] ESP-IDF — MQTT client.**  
ESP-MQTT supports MQTT v5 and TLS-capable transport used by the project.  
https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/protocols/mqtt.html

**[R7] AWS IoT Core — Device Shadow document semantics.**  
Reference pattern for desired/reported/version and stale-state handling; ColdGuard implements its own twin.  
https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-document.html

---

# 75. Final handover checklist

## Safety

- [ ] safety hierarchy.
- [ ] hazard ledger.
- [ ] invariant matrix.
- [ ] default-off dependency understood.

## Controller A

- [ ] threshold.
- [ ] hysteresis.
- [ ] persistence/dwell.
- [ ] physical benchmark.
- [ ] local operation.

## Controller B

- [ ] model/version input.
- [ ] policy threshold.
- [ ] persistence.
- [ ] AIW.
- [ ] physical action same core magnitude.
- [ ] final freeze.

## Command

- [ ] TTL.
- [ ] duplicate.
- [ ] wrong-device.
- [ ] out-of-range.
- [ ] invalid-state.
- [ ] reason codes.

## Verification

- [ ] ACK distinct.
- [ ] electrical verify.
- [ ] thermal verify.
- [ ] cooling-health states.
- [ ] unknown semantics.

## SAFE_LOCAL

- [ ] entry.
- [ ] local control.
- [ ] exit.
- [ ] reconnect reconciliation.

## Security

- [ ] threat model.
- [ ] TLS baseline.
- [ ] device identity.
- [ ] ACL.
- [ ] backend authz.
- [ ] no secrets.
- [ ] negative tests.

## Resilience

- [ ] AI loss.
- [ ] broker loss.
- [ ] backend loss.
- [ ] DB loss policy.
- [ ] PZEM degraded.
- [ ] sensor degraded.
- [ ] reset/watchdog reasoning.

## Final

- [ ] A/B policy integrity.
- [ ] final safety case.
- [ ] residual risks.
- [ ] demo runbook.
- [ ] another member can execute negative/resilience tests.

---

# 76. North star

> **Member D succeeds when ColdGuard remains understandable and safe precisely when something goes wrong.**

> **A good controller is not one that turns cooling on quickly. It is one that knows when it is allowed to act, when it must refuse, how to fall back, how to verify the real physical effect, and how to recover without replaying stale intent.**

> **The strongest control claim of ColdGuard is therefore not “AI controls the Peltier.” It is: predictive advice enters a deterministic safety hierarchy, every remote command is fresh and idempotent, local protection survives remote failure, and every claimed actuation is reconciled against independent electrical and thermal evidence.**
