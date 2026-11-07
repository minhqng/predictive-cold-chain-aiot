# COLDGUARD — HỆ THỐNG BẢO VỆ CHUỖI LẠNH CHỦ ĐỘNG
## AIoT Closed-Loop Engineering · Firmware · Messaging · Digital Twin · Prediction · Control · Recovery

> **Document:** `docs/02-aiot-closed-loop-engineering.md`  
> **Course:** Internet of Things (IoT) — Course Project / Bài tập lớn  
> **Project:** **ColdGuard — Hệ thống bảo vệ chuỗi lạnh chủ động**  
> **Type:** AIoT Execution Contract + Firmware/Backend Engineering Specification + Closed-Loop Reliability Design  
> **Status:** **PROPOSED FREEZE v1.0 — REVIEW CANDIDATE**  
> **Baseline date:** **2026-09-29**  
> **Parents:** `00-project-scope-architecture.md`, `01-physical-measurement-correctness-contract.md`  
> **Children:** `03-verification-experiments-demo.md`, `04-team-execution-plan.md`, `05A/05B/05C/05D`  
> **Normative role:** source of truth for runtime subsystem responsibilities, firmware architecture, acquisition scheduling, telemetry and event semantics, MQTT topic/QoS/retain/session behavior, message identity, freshness, backend ingestion, storage, device-twin state, feature/inference integration, command lifecycle, policy/control execution, response verification, SAFE_LOCAL, reconnect/resynchronization, observability, security enforcement boundaries and software failure/recovery semantics.  
> **Not source of truth for:** exact purchased BOM and physical measurement authority (`00/01`), final experiment repetition counts/statistical tests (`03`), team calendar/ownership (`04`), or member-specific weekly issue breakdown (`05A–05D`).  
> **Hardware constraint:** this engineering contract uses exactly the frozen P0 hardware from Docs 00–01: one dual ESP32-S3R2 board with one primary MCU, DS18B20 ×3, BME280 ×1, MC-38 ×1, PZEM-017 + 50 A/75 mV shunt + MAX3485, one IBT-2, one exact purchased TEC1-12715 SKU, V1 12 V assembly, HS2 6 L chamber and the frozen power/distribution/protection components. It does not reintroduce INA226, a second TEC, discrete MOSFET stages or a 20 L chamber.  
> **Executable source of truth:** source/config may pin exact package versions, environment variables, database migrations, topic ACLs and deployment files. If executable configuration changes a semantic guarantee in this document, the document must change in the same reviewed change.  
> **Change policy:** changing telemetry identity, MQTT delivery assumptions, topic meaning, command freshness/idempotency, twin authority, controller safety path, inference contract, SAFE_LOCAL behavior, storage provenance, or reconnect/resynchronization semantics requires architecture review against Docs 00–01.

> **Engineering thesis.**  
> **ColdGuard does not obtain closed-loop correctness from MQTT, AI, a database, or one ACK in isolation. Correctness is obtained by preserving stable identity and freshness across the software path, separating desired/reported/derived state, allowing prediction only to advise a safety-bounded policy, making actuation idempotent and expiring, and reconciling every claimed cooling action against the physical electrical and thermal evidence defined by Doc 01.**

---

# 0. Executive AIoT execution baseline

## 0.1 The one-sentence rule

> **Treat every network message as delayable/duplicable, every prediction as advisory, every remote command as expiring intent, every ACK as protocol evidence rather than physical proof, and every final cooling claim as valid only after the measured electrical and thermal state reconcile with the requested action.**

---

## 0.2 End-to-end runtime model

```text
PHYSICAL TESTBED
  │
  ├─ DS18B20 ×3
  ├─ BME280
  ├─ MC-38
  └─ PZEM-017 ← MAX3485
          │
          ▼
PRIMARY ESP32-S3R2
  │
  ├─ acquisition
  ├─ quality/freshness
  ├─ applied actuator state
  ├─ local safety / SAFE_LOCAL
  └─ MQTT client
          │
          ▼
ECLIPSE MOSQUITTO / MQTT 5
          │
          ▼
BACKEND APPLICATION
  │
  ├─ ingestion
  ├─ validation / dedup
  ├─ raw + normalized storage
  ├─ current twin
  ├─ events/audit
  ├─ feature state
  ├─ inference adapter
  ├─ policy
  └─ command lifecycle
          │
          ▼
POSTGRESQL + TIMESCALEDB
          │
          ├─ raw evidence
          ├─ normalized telemetry
          ├─ runs
          ├─ predictions
          ├─ commands
          └─ audit/events

MODEL ARTIFACT
  XGBoost
          │
          ▼
risk / warning
          │
          ▼
POLICY / SAFETY GATE
          │
          ▼
command_id + TTL
          │
          ▼
MQTT COMMAND
          │
          ▼
ESP32 VALIDATE / APPLY
          │
          ▼
IBT-2 → TEC
          │
          ├─ PZEM electrical response
          └─ DS18B20 thermal response
                    │
                    ▼
                  VERIFY
```

---

## 0.3 Semantic completion levels

ColdGuard distinguishes these moments:

```text
C0 prediction produced
C1 policy decided action
C2 command created
C3 broker accepted/published path
C4 device received command
C5 device accepted/rejected command
C6 actuator state applied
C7 electrical response observed
C8 thermal response observed
C9 physical action verified / failed verification
```

These states must not be collapsed.

A graph/dashboard that displays:

```text
Cooling = ON
```

must state whether that means:

- desired;
- applied;
- electrically verified;
- thermally verified.

---

## 0.4 Core technology baseline

The project deliberately uses a small technology stack.

### Edge

```text
ESP-IDF on ESP32-S3R2
C/C++
ESP-MQTT
Wi-Fi
TLS-capable MQTT client
```

Reason:

- direct access to ESP32 peripherals and lifecycle;
- deterministic device state;
- first-party MQTT/TLS examples;
- appropriate for low-level safety/fallback.

### Broker

```text
Eclipse Mosquitto
MQTT 5-capable
TLS
authentication
topic ACL
```

Reason:

- one-device/student-scale workload;
- small operational surface;
- standards-oriented MQTT behavior;
- TLS and authentication/ACL support.

### Backend

Preferred baseline:

```text
Python 3.x
FastAPI-class asynchronous web/API framework
modular monolith
```

Reason:

- direct integration with ML tooling;
- simple API/realtime surface;
- one application is sufficient for the workload;
- no benefit from artificial backend microservices.

Exact framework/version is pinned by repo before implementation freeze.

### Storage

```text
PostgreSQL
+
TimescaleDB extension/hypertable where useful
```

Reason:

- relational experiment/audit data;
- transactional state;
- SQL;
- time-series indexing;
- one database technology rather than a separate time-series DB and relational DB.

### ML

```text
Python
XGBoost core model
stable model artifact via save_model()
feature/model versioning
```

XGBoost documentation recommends stable model serialization for long-term model storage rather than Python pickle/memory snapshots.

### Frontend

P0 only needs:

- current state;
- telemetry chart;
- prediction/risk;
- command/policy state;
- event/audit timeline;
- experiment view.

Framework choice is secondary to data semantics.

---

## 0.5 Why no Kafka / Kubernetes / distributed backend

At 1 Hz:

\[
86{,}400\text{ telemetry messages/day/device}
\]

With one P0 device, this is a small workload.

Even at approximately 1 KB serialized/message:

\[
\approx86\text{ MB/day}
\]

before storage/index overhead.

Therefore P0 does not need:

- Kafka;
- Redpanda;
- Kubernetes;
- distributed SQL;
- sharding;
- service mesh;
- CQRS/event-sourcing framework.

The hard problems are:

```text
physical truth
identity
freshness
experiment traceability
safe actuation
recovery semantics
```

not throughput.

---

# 1. Runtime responsibility boundaries

## 1.1 Physical layer — Doc 01 authority

Owns:

- sensor identity;
- measurement meaning;
- applied physical hardware;
- electrical/thermal response;
- hardware safety invariants.

Software must not redefine those semantics.

---

## 1.2 Edge controller

Owns:

- direct sensor acquisition;
- direct actuator pin state;
- local device mode;
- device-side command validation;
- device-side idempotency;
- local fallback;
- telemetry sequence/boot identity.

It does not own:

- ML training;
- final research evaluation;
- backend user authorization;
- experiment statistics.

---

## 1.3 Broker

Owns transport-level MQTT semantics.

The broker does not own:

- business/physical idempotency;
- command legality;
- physical success;
- experiment truth.

---

## 1.4 Backend

Owns:

- message validation;
- dedup persistence;
- raw evidence retention;
- twin materialization;
- experiment/run state;
- prediction invocation;
- policy decision;
- command audit;
- API/realtime projections.

It does not own direct physical truth.

---

## 1.5 ML component

Owns:

- feature transformation;
- versioned model artifact;
- risk/warning inference;
- prediction metadata.

It does not own actuation.

---

## 1.6 Policy/control component

Owns:

- risk/state interpretation;
- safety gating;
- Controller A/B decision;
- command reason;
- allowed requested action.

It does not bypass device validation.

---

# 2. Device boot and lifecycle model

## 2.1 Device modes

Canonical modes:

```text
BOOT
SELF_TEST
ONLINE_NORMAL
ONLINE_DEGRADED
SAFE_LOCAL
FAULT_LOCKOUT
```

Optional internal submodes may exist.

---

## 2.2 BOOT

At reset:

```text
actuator safe/off
→ load immutable/config data
→ initialize GPIO/peripherals
→ establish sensor identities
→ initialize quality state
→ initialize sequence/boot identity
```

No remote predictive command is trusted before boot state is valid.

---

## 2.3 SELF_TEST

Minimum checks:

- expected DS18B20 ROM identities available;
- BME280 availability recorded;
- door input mapped;
- PZEM/RS-485 availability recorded;
- actuator output remains OFF;
- configuration version known.

Not every noncritical sensor must pass to reach degraded mode.

---

## 2.4 ONLINE_NORMAL

Conditions:

- physical state sufficient;
- MQTT connected;
- command freshness valid;
- backend state synchronized enough for normal mode;
- no critical safety fault.

---

## 2.5 ONLINE_DEGRADED

Examples:

- BME280 unavailable;
- one redundant thermal channel unavailable;
- PZEM temporarily unavailable while thermal safety remains possible.

Behavior:

- explicit quality flag;
- predictive/diagnosis capability may be reduced;
- no silent normal confidence.

---

## 2.6 SAFE_LOCAL

Entered when remote predictive path is unavailable/untrusted but local thermal protection remains possible.

Uses deterministic local control.

---

## 2.7 FAULT_LOCKOUT

Used when safe actuation cannot be guaranteed.

Examples:

- invalid critical sensor set;
- actuator electrical anomaly;
- configuration contradiction;
- hardware safety condition.

The exact criteria are control policy state, not broker availability alone.

---

# 3. Acquisition architecture

## 3.1 Acquisition principle

The edge does not simply “read all sensors and publish.”

It creates a coherent physical snapshot.

Concept:

```text
begin acquisition cycle
→ acquire thermal channels
→ acquire BME context
→ acquire door state
→ acquire PZEM branch state
→ assign quality per channel
→ calculate edge-minimal metadata
→ emit telemetry snapshot
```

---

## 3.2 DS18B20 acquisition

Preferred:

```text
broadcast conversion
→ wait according to configured resolution
→ read known T1/T2/T3 ROMs
→ CRC/validity check
```

No array-index identity.

---

## 3.3 BME280 acquisition

At approximately 1 Hz.

Record:

```text
t_air
rh
quality
```

Pressure is not core.

---

## 3.4 MC-38 acquisition

Door is:

- event-driven for transitions;
- included in periodic snapshot as current state.

This allows both event timing and state reconstruction.

---

## 3.5 PZEM acquisition

Baseline:

```text
~1 Hz to 2 Hz
```

depending on stable Modbus polling.

The edge must not block all sensor/actuation logic indefinitely because PZEM does not respond.

Use bounded Modbus timeout.

---

## 3.6 Scheduling

Recommended conceptual tasks:

```text
SensorTask
ElectricalTask
ControlTask
MqttTask
HealthTask
```

The implementation may use ESP-IDF tasks/timers/event loops.

The correctness requirement is priority separation:

> remote networking failure must not starve local safety control.

---

## 3.7 Sampling cadence

P0 target:

| Signal | Target |
|---|---:|
| DS18B20 | ~1 Hz |
| BME280 | ~1 Hz |
| PZEM | ~1–2 Hz |
| door | event + current state |
| telemetry publish | ~1 Hz |
| commands | event-driven |

No architecture benefit exists in 50–100 Hz thermal telemetry.

---

# 4. Snapshot semantics

## 4.1 Telemetry snapshot

A telemetry message represents one logical device-state sample.

Conceptual:

```json
{
  "schema_version": 1,
  "device_id": "coldguard-001",
  "boot_id": "01J...",
  "seq": 12345,
  "captured_at": "...",
  "uptime_ms": 1234567,
  "run_id": "CG-S2-A-001",
  "hardware_config_id": "CG-HW-001",
  "firmware_version": "fw-...",
  "calibration_id": "cal-...",
  "thermal": {},
  "environment": {},
  "door": {},
  "electrical": {},
  "actuation": {},
  "quality": {}
}
```

---

## 4.2 Identity

Required concepts:

```text
device_id
boot_id
seq
```

Backend dedup identity:

```text
(device_id, boot_id, seq)
```

MQTT telemetry schema 1 requires a timezone-aware device `captured_at`.
For clockless Member A serial telemetry, schema 2 requires explicit
`captured_at: null`, device `uptime_ms`, and a `serial_source` object with
the source schema, original frame, timezone-aware gateway receipt time and
`clock_quality: UNAVAILABLE`. Gateway and backend receipt times describe
separate processing steps. Neither establishes the device measurement time
or the ordering of device boots. Schema 2 preserves the source's `UNKNOWN`
quality. Both schemas use the same topic, QoS and logical identity.

---

## 4.3 Why timestamp alone is not dedup identity

Timestamp can:

- drift;
- collide;
- be rounded;
- jump after synchronization.

Therefore timestamp is event time, not unique identity.

---

## 4.4 boot_id

Must distinguish separate device boot sessions.

Acceptable implementations include:

- random UUID generated at boot;
- persistent monotonic boot counter plus device identity;
- other collision-resistant session identity.

The exact method is frozen in firmware implementation.

---

## 4.5 seq

Monotonic within one boot session.

After reboot, seq may reset if `boot_id` changes.

---

# 5. Time semantics

## 5.1 Required times

Distinguish:

```text
captured_at
backend_received_at
db_committed_at
```

Optional command times:

```text
created_at
published_at
device_received_at
ack_at
verified_at
```

---

## 5.2 Edge wall clock

If NTP/synchronization is healthy:

- include UTC captured time.

If not:

- preserve uptime and sequence;
- mark time-sync quality.

Do not fabricate precise UTC.

---

## 5.3 Monotonic duration

Within one boot:

```text
uptime_ms
```

is preferred for edge-local duration.

---

## 5.4 Latency measurement

Command round-trip measured using backend clock:

```text
ack_at - published_at
```

is robust against device clock drift.

Device-event to backend latency requires adequate clock synchronization.

---

# 6. MQTT protocol baseline

## 6.1 Protocol

Baseline:

```text
MQTT 5 preferred
MQTT 3.1.1-compatible subset acceptable only if chosen intentionally
```

MQTT 5 provides:

- session expiry;
- message expiry;
- reason codes;
- richer metadata.

---

## 6.2 QoS reality

OASIS defines:

```text
QoS 0 = at most once
QoS 1 = at least once
QoS 2 = exactly once at MQTT delivery protocol level
```

ColdGuard P0 uses application idempotency even when QoS provides delivery guarantees.

---

## 6.3 Core topic namespace

```text
coldguard/{device_id}/telemetry
coldguard/{device_id}/event
coldguard/{device_id}/state
coldguard/{device_id}/command
coldguard/{device_id}/command_ack
coldguard/{device_id}/health
```

Optional experiment/backend-internal topics require review.

---

## 6.4 Topic ownership

### Device publishes

```text
telemetry
event
state
command_ack
health
```

### Device subscribes

```text
command
```

### Backend publishes

```text
command
```

Backend may publish derived UI data through its own API/realtime channel rather than broker topics.

---

# 7. MQTT QoS policy

| Topic | QoS | Retain | Rationale |
|---|---:|---:|---|
| `telemetry` | 1 | No | avoid avoidable loss; backend dedup handles duplicate |
| `event` | 1 | No | audit-significant event |
| `state` | 1 | Yes, if used as current snapshot | new subscriber may need current device state |
| `command` | 1 | **No** | retained stale actuation is unsafe |
| `command_ack` | 1 | No | lifecycle evidence |
| `health` | 1 | Yes | current connectivity/health projection |

---

## 7.1 Why telemetry QoS 1

QoS 1 can retransmit.

Therefore:

```text
QoS 1
+
backend UNIQUE(device_id, boot_id, seq)
```

is the baseline.

---

## 7.2 Why not QoS 2 as a correctness shortcut

QoS 2 concerns MQTT message delivery.

It does not prove:

- physical side effect happened exactly once;
- application state transition is idempotent;
- stale command is legal.

ColdGuard requires application-layer identity regardless.

---

## 7.3 Command QoS

Command uses QoS 1 plus:

```text
command_id
TTL/expiry
idempotent device handling
expected state/freshness
```

---

# 8. MQTT retained-state contract

## 8.1 Appropriate retained content

Good candidates:

- current health;
- current device state snapshot.

---

## 8.2 Forbidden retained command

`command` topic:

```text
retain = false
```

A new/reconnected device must not receive an old cooling command merely because it subscribed.

---

## 8.3 Clearing retained state

If a retained state topic becomes invalid/retired, deployment procedures must explicitly clear/update it.

---

# 9. MQTT session and expiry

## 9.1 Session Expiry

MQTT 5 can retain session state after disconnection when Session Expiry Interval > 0.

ColdGuard may use a bounded nonzero session expiry for intermittent connectivity.

---

## 9.2 Session is not application history

Broker session state is not the experiment database.

Raw evidence belongs to PostgreSQL.

---

## 9.3 Message Expiry

Commands should use application expiry semantics even if MQTT 5 Message Expiry is also configured.

Defense in depth:

```text
transport message expiry
+
payload expires_at
+
device validation
```

---

# 10. Last Will and connectivity

## 10.1 LWT

Device Last Will on health topic:

```json
{
  "status": "OFFLINE_UNEXPECTED",
  "device_id": "coldguard-001",
  "boot_id": "..."
}
```

Retained if health snapshot strategy uses retained state.

---

## 10.2 Online state

After successful connect:

```text
ONLINE
```

published.

---

## 10.3 LWT limitation

LWT is connectivity evidence.

It is not proof:

- hardware power failed;
- sensor failed;
- actuator failed.

---

# 11. MQTT/TLS baseline

## 11.1 TLS

P0 deployment must support:

```text
MQTT over TLS
broker certificate validation
```

ESP-IDF/ESP-MQTT supports MQTT over TLS examples.

---

## 11.2 Authentication

At least:

- device credential;
- backend credential.

Preferred:

- per-device scoped credential.

No public anonymous command publisher.

---

## 11.3 Broker choice

Eclipse Mosquitto baseline.

Mosquitto supports:

- TLS listeners;
- username/password;
- certificate authentication;
- ACL/dynamic security options.

---

# 12. Broker ACL baseline

Example principal rules:

| Principal | Publish | Subscribe |
|---|---|---|
| `device-coldguard-001` | own telemetry/event/state/ack/health | own command |
| backend ingestion | none or admin/internal only | device telemetry/event/state/ack/health |
| backend command | authorized device command | device ack/state |
| frontend user | none directly | none directly |
| admin | scoped management | scoped |

A device does not get:

```text
coldguard/#
```

full read/write by default.

---

# 13. Backend ingestion contract

## 13.1 Receive

For every MQTT message:

```text
receive
→ identify topic/device
→ parse
→ schema validate
→ semantic validate
→ idempotency check
→ persist raw
→ persist normalized/projection
→ emit/update derived application state
```

---

## 13.2 Raw-before-derived principle

Raw evidence must survive downstream transformation bugs.

Preferred:

```text
raw payload persisted
before/with normalized handling
```

A malformed message may be stored as rejected raw evidence if safe.

---

## 13.3 Backend idempotency

Telemetry unique key:

```text
(device_id, boot_id, seq)
```

Duplicate:

- no second normalized physical sample;
- increment duplicate metric;
- preserve diagnostic metadata if needed.

---

## 13.4 Out-of-order

Older event-time telemetry may be stored historically.

Current twin must not regress blindly.

Twin update guard considers:

```text
boot/session
sequence
event time
quality
```

---

# 14. Storage architecture

## 14.1 `telemetry_raw`

Conceptual:

```text
id
device_id
boot_id
seq
topic
schema_version
captured_at
backend_received_at
raw_payload JSONB
ingest_status
validation_errors
run_id?
created_at
```

Unique:

```text
(device_id, boot_id, seq)
```

for telemetry message identity.

---

## 14.2 `telemetry`

Normalized physical snapshot:

```text
time
device_id
boot_id
seq
run_id

t1_c
t2_c
t3_c
t_air_c
rh_pct
door_state

cooling_voltage_v
cooling_current_a
cooling_power_w
cooling_energy_counter_wh

applied_cooling
applied_duty

thermal_quality
environment_quality
electrical_quality
overall_quality
device_mode

hardware_config_id
firmware_version
calibration_id
schema_version

backend_received_at
```

This is a TimescaleDB hypertable candidate.

---

## 14.3 No legacy two-branch fields

Forbidden P0 normalized fields from old hardware:

```text
current_1
current_2
power_1
power_2
cmd_1
cmd_2
```

Canonical new branch semantics are singular:

```text
cooling_current_a
cooling_power_w
applied_cooling
applied_duty
```

---

## 14.4 `events`

```text
event_id
event_type
device_id
run_id
event_time
received_at
source
severity
correlation_id
payload JSONB
```

Examples:

- door opened/closed;
- sensor degraded;
- SAFE_LOCAL entered;
- command rejected;
- cooling verification failed;
- connectivity restored.

---

## 14.5 `device_twin`

```text
device_id
twin_version

reported_state JSONB
desired_state JSONB
derived_state JSONB

last_reported_at
last_desired_at
last_derived_at

last_boot_id
last_seq
connectivity_state
device_mode

updated_at
```

---

## 14.6 `predictions`

```text
prediction_id
device_id
run_id
prediction_time

model_version
feature_version
horizon_sec

risk_score
calibrated_probability?
warning
decision_threshold
feature_quality

inference_ms
input_window_start
input_window_end
```

---

## 14.7 `commands`

```text
command_id
device_id
run_id

created_at
expires_at
published_at
ack_at
applied_at?
verified_at?

controller_id
policy_version
prediction_id?

requested_action
requested_duty?
reason_code

status
reject_code?
verification_status
```

---

## 14.8 `experiments`

```text
run_id
scenario_id
controller_id
pair_id?

hardware_config_id
firmware_version
backend_version
schema_version
calibration_id
feature_version?
model_version?
policy_version

start_at
end_at

valid
invalid_reason?
notes
```

---

## 14.9 `model_registry`

Minimal:

```text
model_version
feature_version
artifact_path
artifact_sha256
training_dataset_id
training_commit
created_at
metrics_summary
calibration_version?
status
```

---

# 15. TimescaleDB policy

## 15.1 Hypertable

Normalized telemetry may use hypertable keyed by time.

TimescaleDB preserves SQL table semantics while partitioning time-series data into chunks.

---

## 15.2 Raw retention

P0:

> **Keep all raw telemetry for the project.**

Do not enable raw-data deletion merely to demonstrate retention policies.

Dataset size is small.

---

## 15.3 Continuous aggregates

Optional for dashboard/report performance.

They are not source-of-truth evidence.

If used:

- final analysis can always return to raw/normalized samples;
- continuous aggregate refresh policy must not erase needed evidence.

---

# 16. Transactional backend state

## 16.1 Why transactions matter

Certain backend changes should be atomic locally.

Example:

```text
create command audit row
+
record desired twin intent
```

may be committed in one local PostgreSQL transaction before publish.

---

## 16.2 No distributed transaction assumption

Do not attempt one ACID transaction across:

```text
PostgreSQL
+
MQTT broker
+
ESP32
+
physical TEC
```

Those are independent boundaries.

---

## 16.3 State reconciliation instead of 2PC

Use:

- durable local intent;
- message identity;
- ACK;
- reported state;
- physical verification;
- timeout/reconciliation.

---

# 17. Digital Twin contract

## 17.1 Scope

ColdGuard Twin = **testbed/device twin**.

Not:

- whole supply-chain twin;
- CFD simulation;
- biological shelf-life twin.

---

## 17.2 `reported`

Owned by physical/device observations.

Example:

```json
{
  "thermal": {
    "t1_c": 7.1,
    "t2_c": 7.4,
    "t3_c": 7.8
  },
  "environment": {
    "t_air_c": 7.5,
    "rh_pct": 84.2
  },
  "door": "CLOSED",
  "electrical": {
    "voltage_v": 11.9,
    "current_a": 10.8,
    "power_w": 128.5
  },
  "actuation": {
    "applied": "ON",
    "duty": 1.0
  },
  "mode": "ONLINE_NORMAL",
  "boot_id": "...",
  "seq": 12345
}
```

---

## 17.3 `desired`

Owned by current valid backend/policy intent.

Example:

```json
{
  "cooling": {
    "state": "ON",
    "duty": 1.0,
    "command_id": "...",
    "expires_at": "..."
  }
}
```

---

## 17.4 `derived`

Computed state.

Example:

```json
{
  "thermal": {
    "mean_c": 7.43,
    "max_c": 7.8,
    "gradient_c": 0.7,
    "slope_c_per_min": 0.12
  },
  "prediction": {
    "risk_score": 0.74,
    "horizon_sec": 120,
    "model_version": "..."
  },
  "cooling_health": {
    "state": "HEALTHY_RESPONSE"
  },
  "quality": "VALID"
}
```

---

## 17.5 Desired does not overwrite reported

This is a hard rule.

```text
desired ON
```

cannot set:

```text
reported.applied = ON
```

without device evidence.

---

## 17.6 Derived does not overwrite physical fields

A model prediction cannot replace raw sensor truth.

---

## 17.7 Version/freshness

Twin state includes:

- update times;
- last boot/seq;
- twin version.

AWS IoT Device Shadow uses desired/reported/version semantics and shows why stale/out-of-order versions need explicit handling. ColdGuard implements a lightweight equivalent, not the AWS service itself.

---

# 18. Event model

## 18.1 State versus event

Telemetry snapshot:

> current observed state.

Event:

> something meaningful happened.

Examples:

```text
DOOR_OPENED
DOOR_CLOSED
SAFE_LOCAL_ENTERED
SAFE_LOCAL_EXITED
SENSOR_DEGRADED
PZEM_UNAVAILABLE
COMMAND_ACCEPTED
COMMAND_REJECTED
COOLING_ELECTRICAL_VERIFIED
COOLING_THERMAL_VERIFIED
COOLING_VERIFICATION_FAILED
```

---

## 18.2 Event identity

```text
event_id
```

must be unique.

Event may include:

```text
caused_by_command_id
prediction_id
correlation_id
```

where relevant.

---

# 19. Prediction engineering contract

## 19.1 Separation of training and inference

Training pipeline lives under ML ownership.

Runtime consumes a frozen artifact.

Runtime must not retrain opportunistically from live telemetry.

---

## 19.2 Model artifact

XGBoost:

- save model using official model serialization;
- record `model_version`;
- record artifact hash;
- keep feature pipeline version.

Do not use Python pickle as the long-term only source of truth.

---

## 19.3 Feature contract

Each model has a frozen ordered feature schema.

Example families:

```text
thermal instantaneous
thermal temporal
door context
environment context
electrical context
actuation context
recovery/exposure
quality/context
```

---

## 19.4 Past-only

At prediction time \(t\):

```text
feature input <= t
```

No future telemetry.

---

## 19.5 Input window

Prediction record preserves:

```text
input_window_start
input_window_end
```

This makes leakage/audit possible.

---

## 19.6 Horizon

`horizon_sec` is model metadata.

Do not infer horizon from model file name alone.

---

## 19.7 Risk score

Default semantic:

```text
risk_score
```

If calibration is valid:

```text
calibrated_probability
```

can be added.

---

## 19.8 Model health

Runtime model status:

```text
READY
UNAVAILABLE
FEATURE_INVALID
VERSION_MISMATCH
DEGRADED
```

AI failure never disables Controller A/SAFE_LOCAL.

---

# 20. Inference deployment

## 20.1 P0 recommendation

Prefer:

```text
backend process loads frozen XGBoost model
+
feature adapter
```

or a closely coupled inference module/package.

A separate network ML microservice is optional.

Reason:

- one device;
- low inference rate;
- fewer failure boundaries;
- easier reproducibility.

---

## 20.2 When a separate service is justified

Only if:

- team ownership strongly benefits;
- independent lifecycle is needed;
- multiple model runtimes exist;
- isolation is required.

If separate:

- version protocol;
- define timeout;
- define AI unavailable behavior.

---

## 20.3 Inference cadence

At most around telemetry cadence unless event-triggered.

Running inference 100 times/sec on 1 Hz physical data adds no information.

---

# 21. Policy input contract

Policy receives a structured snapshot, not arbitrary raw payload.

Concept:

```text
physical_quality
thermal_state
door_context
electrical_state
applied_actuation
prediction
prediction_age
device_mode
connectivity
```

---

## 21.1 Preconditions for predictive action

All must be true:

```text
physical state sufficiently valid
prediction version recognized
prediction fresh
policy version recognized
device online/synchronized enough
command action within validated operating envelope
no higher-priority safety fault
```

---

# 22. Safety hierarchy

Immutable ordering:

```text
1. physical/electrical safety
2. deterministic local protection
3. fault/degraded handling
4. reactive policy
5. predictive intervention
6. energy optimization
```

A lower layer never overrides a higher one.

---

# 23. Policy state machine

Canonical high-level states:

```text
NORMAL
WATCH
PREEMPTIVE_COOLING
CRITICAL_PROTECTION
FAULT
SAFE_LOCAL
```

---

## 23.1 NORMAL

- state valid;
- no critical/predictive trigger;
- cooling according to baseline need.

---

## 23.2 WATCH

- trajectory/risk elevated;
- insufficient condition for intervention;
- increased attention/persistence.

---

## 23.3 PREEMPTIVE_COOLING

Predictive condition valid.

Action may begin before reactive threshold.

---

## 23.4 CRITICAL_PROTECTION

Reactive/hard threshold reached.

Deterministic protection dominates.

---

## 23.5 FAULT

A physical/control fault invalidates normal policy.

Action depends on fault type and safe state.

---

## 23.6 SAFE_LOCAL

Remote intelligence unavailable/untrusted.

Device applies local deterministic threshold/hysteresis.

---

# 24. Hysteresis, persistence and anti-chatter

## 24.1 Hysteresis

Use distinct ON/OFF boundaries when relevant:

```text
upper
lower
```

---

## 24.2 Persistence

Prediction/risk may require:

```text
risk > threshold for N seconds/samples
```

before transition.

---

## 24.3 Minimum dwell

Optional:

- minimum ON time;
- minimum OFF time;

if characterization shows chattering risk.

---

## 24.4 No magic constants

Final values come from:

- plant characterization;
- pilot experiment;
- safety constraints.

---

# 25. Controller A

## 25.1 Purpose

Scientific baseline and local fallback basis.

---

## 25.2 Input

Primarily valid thermal state.

---

## 25.3 Decision

```text
threshold
+
hysteresis
+
optional persistence/dwell
```

---

## 25.4 Output

Same allowed cooling action family as Controller B during core A/B campaign.

---

# 26. Controller B

## 26.1 Purpose

Use predictive warning to intervene earlier.

---

## 26.2 Difference from A

Core study should make:

```text
timing
```

the primary difference.

Not:

```text
A uses weak cooling
B uses stronger cooling
```

unless that is an explicitly separate study.

---

## 26.3 Input

- same physical state;
- predictive risk;
- quality/freshness;
- policy.

---

## 26.4 Output

Safety-bounded desired action.

---

# 27. Actionable intervention window

Concept:

\[
AIW=t_{critical}-t_{warning}-t_{response}-t_{latency}
\]

Where:

- `t_warning`: predictive warning time;
- `t_critical`: reactive critical boundary time;
- `t_response`: physical response delay;
- `t_latency`: sensing/inference/policy/command overhead.

AIW must be computed from measured/system timestamps, not imagined.

---

# 28. Command contract

## 28.1 Canonical command

```json
{
  "schema_version": 1,
  "command_id": "uuid",
  "device_id": "coldguard-001",
  "created_at": "...",
  "expires_at": "...",
  "controller_id": "PREDICTIVE",
  "policy_version": "policy-...",
  "prediction_id": "...",
  "reason_code": "PREDICTED_CRITICAL",
  "action": {
    "cooling": "ON",
    "duty": 1.0
  }
}
```

---

## 28.2 Required fields

- stable `command_id`;
- target device;
- issue/create time;
- expiry;
- requested action;
- policy provenance;
- reason.

---

## 28.3 Optional

- expected device/twin version;
- prediction ID;
- run ID;
- experiment controller ID.

---

# 29. Command validation

Device validates:

```text
schema valid
AND device_id matches
AND command_id recognized/new
AND not expired
AND action in allowed range
AND local safety permits
AND local state sufficiently valid
```

Backend authorization does not replace device validation.

---

# 30. Command idempotency

## 30.1 Duplicate same command_id

Must not create a second independent actuation.

Device returns current/canonical result.

---

## 30.2 New command_id same action

Represents a new logical control instruction.

---

## 30.3 Idempotency memory

Device keeps recent command identity/result long enough for expected retransmission/reconnect behavior.

Exact retention size is implementation detail.

---

# 31. Command freshness

## 31.1 Expiry

If:

```text
now > expires_at
```

reject.

---

## 31.2 No retained commands

Transport configuration must not create old retained actuation.

---

## 31.3 Reconnect

After reconnect, device does not blindly reapply an old desired command.

It reconciles:

- freshness;
- current physical state;
- current mode.

---

# 32. Command ACK

## 32.1 ACK types

Conceptual:

```text
ACCEPTED
REJECTED
DUPLICATE_CANONICAL
EXPIRED
SAFETY_BLOCKED
INVALID_STATE
OUT_OF_RANGE
```

---

## 32.2 ACK is not physical verification

ACK means:

> device handled the command according to protocol/local validation.

It does not mean:

> chamber cooled.

---

## 32.3 ACK payload

Should include:

```text
command_id
device_id
boot_id
seq/context
status
reason/reject_code
applied_state
device_mode
ack_time / uptime
```

---

# 33. Command lifecycle

Backend status state machine:

```text
CREATED
  ↓
VALIDATED
  ↓
PUBLISHED
  ↓
ACK_ACCEPTED
  ├→ EXECUTED
  │    ↓
  │ ELECTRICAL_VERIFIED
  │    ↓
  │ THERMAL_VERIFIED
  │    ↓
  │ VERIFIED
  │
  └→ FAILED_VERIFICATION

alternate:
ACK_REJECTED
EXPIRED
PUBLISH_FAILED
UNKNOWN
```

Not every internal status requires a separate MQTT message.

---

# 34. Unknown command outcome

If backend publishes command then loses connectivity:

```text
did device apply?
```

may be UNKNOWN.

Backend must not assume:

```text
network error = command not applied
```

Reconcile with:

- command ACK after reconnect;
- device reported applied state;
- electrical/thermal telemetry;
- expiry.

---

# 35. Physical verification service

## 35.1 Electrical verification

After accepted ON command:

```text
within electrical response window
current/power should enter characterized active envelope
```

If not:

```text
ELECTRICAL_RESPONSE_MISSING
```

candidate.

---

## 35.2 Thermal verification

After electrical verification:

```text
within thermal response window
thermal trajectory should show expected response
```

Window comes from Doc 01 characterization.

---

## 35.3 Verification status

Canonical:

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

# 36. Cooling-health derived state

Map Doc 01 states:

```text
HEALTHY_RESPONSE
ELECTRICAL_RESPONSE_MISSING
THERMAL_EFFECTIVENESS_DEGRADED
CONTROL_ELECTRICAL_ANOMALY
UNKNOWN
```

Backend stores:

- state;
- confidence/quality;
- evidence window;
- reason;
- policy version.

---

# 37. SAFE_LOCAL contract

## 37.1 Trigger conditions

Examples:

- broker disconnected beyond grace;
- backend heartbeat/state invalid;
- AI unavailable and remote policy depends on it;
- twin synchronization insufficient;
- remote command path not trusted.

---

## 37.2 Local inputs

Only locally available validated state.

At minimum:

- DS18B20 thermal state;
- local config;
- actuator state.

---

## 37.3 Local policy

```text
upper threshold → cooling ON
lower threshold → cooling OFF
```

with hysteresis and safety checks.

---

## 37.4 Cloud independence

SAFE_LOCAL must run without:

- MQTT response;
- database;
- XGBoost;
- frontend.

---

## 37.5 Local telemetry buffer

If practical:

- buffer a bounded number of telemetry/events;
- preserve identity/order;
- replay after reconnect.

Buffering is desirable but must not threaten local control resources.

---

# 38. Exit SAFE_LOCAL

Conditions:

```text
network stable
broker connected
backend/twin synchronized
current physical telemetry valid
no stale command pending
AI healthy if predictive mode required
```

Then:

```text
SAFE_LOCAL
→ ONLINE_NORMAL/DEGRADED
```

No immediate stale desired-state actuation.

---

# 39. Offline telemetry replay

## 39.1 Identity preserved

Replayed records keep original:

```text
boot_id
seq
captured_at
```

Backend `received_at` will be later.

---

## 39.2 Current twin guard

Replay must not make current twin travel backward.

Historical DB stores it.

Twin update rejects/regards older sequence as historical.

---

# 40. Sensor degraded behavior

## 40.1 One DS18B20 missing

```text
quality = DEGRADED
```

Possible:

- Controller A conservative fallback;
- prediction disabled unless model validated for missing channel.

---

## 40.2 Multiple key thermal sensors missing

Predictive control disabled.

Potential safe action depends on policy and remaining trustworthy state.

---

## 40.3 BME unavailable

Thermal protection may continue.

RH/BME-dependent features unavailable.

---

## 40.4 Door unavailable

Temperature control can continue.

Door-context inference/experiment validity affected.

---

## 40.5 PZEM unavailable

Thermal protection may continue.

Physical electrical verification and cooling-health confidence degrade.

---

# 41. AI unavailable behavior

If inference fails:

```text
Controller B unavailable
→ Controller A / SAFE_LOCAL
```

Do not cache one old risk score indefinitely.

---

# 42. Backend unavailable behavior

Device:

- continues local control;
- optionally buffers telemetry.

Backend restart:

- loads DB state;
- reconnects broker;
- receives current state;
- reconciles before predictive control.

---

# 43. Database unavailable behavior

Backend must not pretend command/audit durability if DB write is required and unavailable.

Preferred:

- stop new predictive commands;
- device remains local-safe;
- ingestion can bounded-buffer only if implementation supports it safely.

---

# 44. Broker unavailable behavior

Backend cannot remotely command device.

Device enters/keeps SAFE_LOCAL.

No alternative direct HTTP-to-device bypass is introduced.

---

# 45. Digital Twin reconciliation

On device reconnect:

1. receive reported current state;
2. compare to stored twin;
3. update current boot/seq;
4. invalidate expired desired commands;
5. reconcile command records;
6. resume prediction only with fresh state.

---

# 46. Twin version semantics

Every twin materialization update increments:

```text
twin_version
```

A version is backend projection version, not physical time.

Do not use twin version as sensor sequence.

---

# 47. API surface

P0 API:

```text
GET /api/devices
GET /api/devices/{device_id}/state
GET /api/devices/{device_id}/telemetry
GET /api/devices/{device_id}/events

GET /api/runs
GET /api/runs/{run_id}
GET /api/runs/{run_id}/telemetry
GET /api/runs/{run_id}/predictions
GET /api/runs/{run_id}/commands
GET /api/runs/{run_id}/compare

GET /api/commands/{command_id}
GET /api/incidents
```

---

## 47.1 Manual command endpoint

If exposed:

```text
POST /api/devices/{device_id}/commands
```

must:

- authenticate;
- authorize;
- validate allowed experimental mode;
- create audit record;
- use same command lifecycle/policy guard.

No debug endpoint directly bypasses safety layer in the release profile.

---

# 48. Realtime frontend

Preferred simple options:

- WebSocket;
- SSE.

Core requirement:

```text
approximately 1 Hz live state
```

No need for high-rate chart streaming.

---

# 49. Dashboard semantic rules

UI must visually distinguish:

```text
desired cooling
applied cooling
electrically verified cooling
thermally verified cooling
```

A single green toggle labeled “ON” is misleading.

---

## 49.1 Required surfaces

### Physical state

- T1/T2/T3;
- Tmean/gradient;
- RH;
- door.

### Electrical

- V/I/P;
- applied actuation.

### Prediction/control

- risk;
- warning;
- Controller A/B;
- reason code;
- command lifecycle.

### Reliability

- device mode;
- MQTT connectivity;
- sensor quality;
- SAFE_LOCAL;
- last seen.

---

# 50. Experiment integration

## 50.1 run_id

All report-grade data during a run include:

```text
run_id
```

---

## 50.2 Controller ID

```text
REACTIVE
PREDICTIVE
```

plus version.

---

## 50.3 Pair ID

Paired A/B experiment may use:

```text
pair_id
```

for analysis.

---

## 50.4 Experiment start

Before start:

- hardware config known;
- current mode valid;
- telemetry stable;
- run manifest created.

---

## 50.5 Experiment end

Backend freezes:

- end time;
- validity pending/final;
- reason;
- versions.

---

# 51. Dataset export

Person B needs deterministic export.

Export manifest includes:

```text
dataset_id
query/hash
run IDs
time interval
schema version
hardware configs
calibration IDs
export time
git/backend commit
```

---

## 51.1 No notebook-only hidden filters

Filters that remove physical records must be expressed in reusable code/config and logged.

---

# 52. Model registry and promotion

## 52.1 Candidate

Trained artifact awaiting evaluation.

---

## 52.2 Approved for offline evaluation

May be used for held-out prediction generation.

---

## 52.3 Approved for shadow mode

Runtime inference visible but cannot trigger physical actuation.

---

## 52.4 Approved for Controller B

Only after:

- evaluation pass;
- feature contract match;
- calibration semantics known;
- safety integration pass;
- shadow mode pass.

---

# 53. Shadow mode

Before predictive actuation:

```text
model predicts
policy decides hypothetical action
but device receives no predictive command
```

Log:

- predicted intervention time;
- hypothetical action;
- Controller A actual path.

This validates end-to-end semantics without physical AI actuation.

---

# 54. Security architecture

## 54.1 Security objectives

- device authenticity;
- encrypted transport;
- least privilege;
- command integrity;
- replay resistance;
- auditability;
- degraded/fallback behavior.

---

## 54.2 Device identity

Do not trust JSON `device_id` alone.

Broker credential/connection identity must map to authorized device topic namespace.

---

## 54.3 Secrets

No real credential committed to repo.

Use:

- environment/secrets file excluded from source;
- dev example config without secret.

---

## 54.4 TLS

Broker certificate validation required in secure profile.

Mutual TLS is optional/hardening if time permits.

---

## 54.5 RBAC

Backend user roles:

```text
VIEWER
OPERATOR
EXPERIMENTER
ADMIN
```

At minimum distinguish:

- read;
- command/experiment;
- security/admin.

---

# 55. Threat model

| Threat | Engineering response |
|---|---|
| forged telemetry | authenticated broker principal + topic ACL + schema |
| forged command | backend authz + broker ACL + device validation |
| replayed command | command ID + TTL + idempotency |
| duplicate QoS delivery | dedup/idempotency |
| stale state | seq/time/freshness |
| model unavailable | Controller A/SAFE_LOCAL |
| broker unavailable | SAFE_LOCAL |
| DB unavailable | stop new durable remote control |
| malformed payload | schema/semantic rejection |
| wrong device topic | topic-device identity validation |
| credential leakage | scoped credentials/rotation procedure |
| dashboard bug | UI non-authoritative |
| stale twin | sequence/version guard |

---

# 56. Observability

Observability explains system behavior.

It does not become control truth.

---

## 56.1 Metrics

Minimum:

```text
mqtt_connected_devices
mqtt_messages_received_total
mqtt_messages_invalid_total
mqtt_messages_duplicate_total
mqtt_messages_out_of_order_total

ingestion_latency_ms
db_write_latency_ms
db_errors_total

telemetry_last_age_seconds
prediction_inference_ms
prediction_errors_total

commands_created_total
commands_rejected_total
command_ack_latency_ms
command_verify_latency_ms
command_expired_total

safe_local_entries_total
sensor_degraded_total
pzem_errors_total
```

---

## 56.2 Structured logs

Fields:

```text
timestamp
level
service
device_id
run_id
boot_id
seq
command_id
prediction_id
correlation_id
event_type
reason_code
```

Do not log:

- secrets;
- passwords;
- private keys.

---

## 56.3 Trace/correlation

OpenTelemetry can provide distributed traces.

Messaging semantic conventions remain evolving/development in current OpenTelemetry documentation, so business IDs must not depend on OTel naming stability.

Use:

```text
correlation_id
command_id
prediction_id
run_id
```

as durable domain/evidence identities.

---

# 57. Health/readiness semantics

## 57.1 Backend liveness

Answers:

> Is the process alive?

Not:

> Are all physical dependencies healthy?

---

## 57.2 Backend readiness

May require:

- config valid;
- DB usable;
- broker subscription initialized.

---

## 57.3 Device health

Separate:

```text
connectivity
sensor quality
electrical observation
device mode
```

Do not collapse to one Boolean.

---

# 58. Error taxonomy

## Protocol

```text
INVALID_JSON
UNSUPPORTED_SCHEMA
DEVICE_ID_MISMATCH
DUPLICATE_MESSAGE
OUT_OF_ORDER
```

## Physical-quality

```text
SENSOR_INVALID
PZEM_UNAVAILABLE
PZEM_CONFIG_INVALID
THERMAL_STATE_INVALID
```

## Command

```text
COMMAND_EXPIRED
COMMAND_DUPLICATE
COMMAND_OUT_OF_RANGE
COMMAND_SAFETY_BLOCKED
COMMAND_STATE_STALE
COMMAND_UNAUTHORIZED
```

## AI

```text
MODEL_UNAVAILABLE
FEATURE_INVALID
MODEL_VERSION_MISMATCH
```

## Infrastructure

```text
BROKER_UNAVAILABLE
DB_UNAVAILABLE
BACKEND_UNAVAILABLE
```

---

# 59. Reason codes

Control/audit reason codes:

```text
THRESHOLD_HIGH
THRESHOLD_RECOVERED
PREDICTED_CRITICAL
RISK_PERSISTENT
DOOR_DISTURBANCE
ELECTRICAL_RESPONSE_MISSING
THERMAL_EFFECTIVENESS_DEGRADED
CONTROL_ELECTRICAL_ANOMALY
SENSOR_DEGRADED
AI_UNAVAILABLE
NETWORK_UNAVAILABLE
BACKEND_UNAVAILABLE
COMMAND_REJECTED_STALE
COMMAND_REJECTED_DUPLICATE
COMMAND_REJECTED_RANGE
COMMAND_REJECTED_SAFETY
RECOVERY_VERIFIED
RECOVERY_FAILED
SAFE_LOCAL_ENTER
SAFE_LOCAL_EXIT
```

---

# 60. Versioning rules

## 60.1 `schema_version`

Changes when wire/data semantics break compatibility.

---

## 60.2 `firmware_version`

Every evidence-grade run records it.

---

## 60.3 `hardware_config_id`

From Docs 00–01.

---

## 60.4 `calibration_id`

Physical calibration/check bundle.

---

## 60.5 `feature_version`

Exact feature definition/order/window.

---

## 60.6 `model_version`

Model artifact identity.

---

## 60.7 `policy_version`

Controller thresholds, persistence, safety/decision parameters.

---

## 60.8 Backend/repo version

Git commit/tag or deploy version recorded in experiment manifest.

---

# 61. Schema evolution

Prefer additive optional changes while compatible.

Breaking change requires new `schema_version`.

Backend must not silently parse an unknown incompatible schema “best effort” into normal state.

Unknown incompatible version:

```text
reject/quarantine
+
visible metric/log
```

---

# 62. Telemetry quality payload

Concept:

```json
{
  "thermal": "VALID",
  "environment": "VALID",
  "door": "VALID",
  "electrical": "VALID",
  "overall": "VALID",
  "time_sync": "SYNCED"
}
```

If degraded:

```json
{
  "thermal": "DEGRADED",
  "missing": ["T3"]
}
```

---

# 63. Command topic payload example

```json
{
  "schema_version": 1,
  "command_id": "01K...",
  "device_id": "coldguard-001",
  "created_at": "2026-09-29T07:00:00Z",
  "expires_at": "2026-09-29T07:00:10Z",
  "run_id": "CG-S2-B-004",
  "controller_id": "PREDICTIVE",
  "policy_version": "policy-v3",
  "prediction_id": "pred-...",
  "reason_code": "PREDICTED_CRITICAL",
  "action": {
    "cooling": "ON",
    "duty": 1.0
  }
}
```

---

# 64. ACK example

```json
{
  "schema_version": 1,
  "command_id": "01K...",
  "device_id": "coldguard-001",
  "boot_id": "boot-...",
  "status": "ACCEPTED",
  "reason_code": "OK",
  "applied": {
    "cooling": "ON",
    "duty": 1.0
  },
  "device_mode": "ONLINE_NORMAL",
  "uptime_ms": 1234567
}
```

---

# 65. State topic example

```json
{
  "schema_version": 1,
  "device_id": "coldguard-001",
  "boot_id": "boot-...",
  "seq": 12345,
  "mode": "ONLINE_NORMAL",
  "reported": {
    "cooling": "ON",
    "duty": 1.0
  },
  "quality": "VALID"
}
```

---

# 66. Health topic example

```json
{
  "device_id": "coldguard-001",
  "status": "ONLINE",
  "mode": "ONLINE_NORMAL",
  "boot_id": "boot-...",
  "firmware_version": "fw-v...",
  "last_seq": 12345
}
```

---

# 67. Policy input freshness

Example conceptual constraints:

```text
telemetry_age <= T_state_max
prediction_age <= T_pred_max
command_age <= TTL
```

Exact numbers are derived after physical response/latency characterization.

No arbitrary fixed 5-minute TTL.

---

# 68. Policy anti-chatter

Track:

```text
last_transition_at
last_action
state
risk persistence
```

Do not toggle on each noisy sample.

---

# 69. Energy-aware extension

Conditional after core.

Candidate action set:

```text
OFF
LOW
MEDIUM
HIGH
```

Mappings are characterization-derived.

Objective may consider:

\[
J =
\alpha E_{thermal}
+\beta E_{cooling}
+\gamma Risk
+\delta N_{switch}
\]

But hard safety is a constraint, not a weighted preference.

---

# 70. PWM extension

If enabled:

- duty range validated;
- frequency documented;
- PZEM measurement semantics characterized;
- V1/IBT-2 behavior stable.

P0 A/B does not require multi-level PWM.

---

# 71. Reproducible deployment

Recommended local deployment:

```text
docker compose
├─ mosquitto
├─ postgres-timescale
├─ backend
└─ optional frontend
```

ML artifact mounted/packaged reproducibly.

Firmware built separately with pinned ESP-IDF/component versions.

---

# 72. Environment profiles

## `dev`

- developer convenience;
- verbose logs;
- local credentials.

## `integration`

- real broker/DB;
- test device/simulator.

## `experiment`

- frozen versions;
- clean data namespace;
- minimal debug intervention.

## `demo`

- stable UI;
- reproducible configuration;
- security baseline.

---

# 73. Device simulator

A software simulator may be used for:

- MQTT contract;
- duplicate/reorder tests;
- backend load;
- command state machine.

It cannot replace real hardware proof for:

- electrical response;
- thermal response;
- sensor calibration;
- physical closed-loop outcome.

---

# 74. Failure windows

For each remote command consider:

```text
W1 before publish
W2 published, before device receive
W3 device received, before ACK
W4 actuator applied, ACK lost
W5 electrical effect occurred, network lost
W6 thermal effect occurred, backend unaware
```

Design must make each window reconcilable or explicitly UNKNOWN.

---

# 75. Failure window W1

Command DB intent exists but publish fails.

Status:

```text
PUBLISH_FAILED / RETRYABLE
```

Do not mark sent.

---

# 76. Failure window W2

Broker accepted, device offline.

Command may wait depending session/subscription semantics but must still expire.

Expired command cannot actuate later.

---

# 77. Failure window W3

Device receives and applies, response lost.

Backend outcome unknown.

Reconcile with reported state/telemetry.

---

# 78. Failure window W4

Device applies and ACK lost.

Duplicate QoS command may arrive.

Same `command_id` returns canonical idempotent result.

---

# 79. Failure window W5/W6

Physical response exists but backend disconnected.

After reconnect:

- buffered/replayed telemetry;
- reported current state;
- command audit reconciliation.

No second physical action solely because ACK was missing.

---

# 80. Backend command retry policy

Only retry publish while command remains semantically valid.

Do not create new command ID for a transport retry of the same logical command.

---

# 81. Stale desired-state policy

Desired state may remain in twin for audit, but expired desired action is not executable intent.

Represent:

```text
desired.status = EXPIRED
```

or clear active desired action.

---

# 82. Safety invariants at software layer

## SW-SAFE-001

AI model cannot publish MQTT command directly.

## SW-SAFE-002

Expired command cannot execute.

## SW-SAFE-003

Duplicate command ID cannot create duplicate actuation.

## SW-SAFE-004

Invalid/stale physical input cannot trigger predictive action.

## SW-SAFE-005

Controller B cannot bypass local device safety.

## SW-SAFE-006

Cloud/network failure cannot remove local Controller A/SAFE_LOCAL protection.

## SW-SAFE-007

Desired state cannot overwrite reported state.

## SW-SAFE-008

ACK cannot be labeled physical verification.

## SW-SAFE-009

Electrical response cannot be labeled thermal success.

## SW-SAFE-010

Unknown state cannot be silently converted to success.

---

# 83. Liveness obligations

## SW-LIVE-001

If broker/network recovers, device eventually reconnects or exposes persistent failure.

## SW-LIVE-002

If backend/DB recovers, ingestion eventually resumes.

## SW-LIVE-003

After reconnect, twin eventually reflects current boot/seq state.

## SW-LIVE-004

Pending command eventually reaches terminal:

```text
VERIFIED
FAILED
REJECTED
EXPIRED
UNKNOWN_VISIBLE
```

not indefinite silent limbo.

## SW-LIVE-005

A physical run eventually becomes:

```text
VALID
INVALID
ABORTED
```

with reason.

---

# 84. API authorization matrix

| Capability | VIEWER | OPERATOR | EXPERIMENTER | ADMIN |
|---|---:|---:|---:|---:|
| view state | ✓ | ✓ | ✓ | ✓ |
| view runs/evidence | ✓ | ✓ | ✓ | ✓ |
| manual allowed command | — | limited | ✓ | ✓ |
| create experiment | — | limited | ✓ | ✓ |
| modify policy config | — | — | controlled | ✓ |
| manage credentials | — | — | — | ✓ |

Exact application auth implementation may be simplified for coursework but command authorization must be real/testable.

---

# 85. Audit requirements

Every remote action should answer:

```text
who/what caused it?
when?
which policy?
which model/prediction?
which run?
what command ID?
did device accept?
what electrical response?
what thermal response?
what final verification?
```

---

# 86. Evidence trace example

```text
run_id CG-S2-B-004
  ↓
prediction pred-901
  risk_score 0.81
  model model-v4
  horizon 120s
  ↓
policy policy-v3
  reason PREDICTED_CRITICAL
  ↓
command cmd-771
  expires 10s
  ↓
ACK ACCEPTED
  ↓
PZEM current rises
  ↓
thermal slope improves
  ↓
VERIFIED
```

This is the central demonstrable closed-loop trace.

---

# 87. Performance expectations

ColdGuard is low-throughput.

Performance goals should target:

- stable 1 Hz ingestion;
- low command latency relative to plant dynamics;
- zero dropped evidence under expected campaign;
- bounded reconnect;
- responsive dashboard.

Do not report “million messages/sec” as relevant success.

---

# 88. Latency budget

Conceptual:

\[
T_{total}
=
T_{sample}
+T_{publish}
+T_{ingest}
+T_{feature}
+T_{infer}
+T_{policy}
+T_{command}
+T_{device}
\]

The important question is:

```text
T_total << physical intervention window
```

not absolute web-scale latency.

---

# 89. Local buffer sizing

If 1 Hz telemetry and 30 minutes offline:

\[
1800\text{ snapshots}
\]

At ~1 KB each:

\[
\approx1.8\text{ MB}
\]

This is an order-of-magnitude planning point.

Actual buffer design must consider available flash/PSRAM/endurance.

Do not persist high-frequency logs indefinitely to flash without wear consideration.

---

# 90. ESP32 storage caution

The purchased board includes W25Q32 according to BOM description.

Exact wiring/usage must be verified.

Local buffering should prefer:

- bounded memory buffer;
- controlled flash persistence only if necessary.

Do not assume external flash is freely available to firmware without confirming board integration.

---

# 91. ESP-IDF watchdog/task principles

Local safety task must not be blocked by:

- MQTT reconnect loop;
- database/network concept;
- slow PZEM retry.

Bound timeouts.

Use watchdog appropriately.

Exact FreeRTOS priorities are implementation details.

---

# 92. PZEM polling failure

If Modbus poll times out:

```text
electrical_quality = DEGRADED/INVALID
```

Do not keep last current as if fresh.

Last known historical value may remain in UI with age.

---

# 93. Sensor staleness display

UI should display:

- value;
- age;
- quality.

A stale “7.2°C” without age can be unsafe/misleading.

---

# 94. Backend model staleness

Each inference record is immutable.

Current risk projection selects the latest valid prediction only.

Older risk remains historical.

---

# 95. Twin derived-state provenance

Derived state includes:

```text
source seq/time
feature_version
model_version
policy_version
computed_at
```

where applicable.

---

# 96. Data retention

P0:

- keep raw entire project;
- backup before final campaign;
- do not auto-drop evidence;
- optional continuous aggregates for UI.

---

# 97. Backup/restore

At least:

- DB dump/backup;
- model artifacts;
- experiment manifests;
- broker config;
- firmware release artifact/config.

Final evidence must survive one developer laptop loss.

---

# 98. Configuration management

Config classes:

```text
device config
broker config
backend config
hardware config
calibration config
experiment config
feature config
model config
policy config
security config
```

Do not hide experiment-critical thresholds in source literals.

---

# 99. Environment variable principle

Secrets/configurable deployment values in environment/secrets.

Research semantics such as:

- threshold;
- horizon;
- policy version;

must still be captured in versioned experiment configuration, not ephemeral env only.

---

# 100. Anti-patterns

## AP-01

```text
QoS1 therefore duplicate impossible
```

False.

## AP-02

```text
ACK therefore TEC cooled
```

False.

## AP-03

```text
desired == reported
```

False.

## AP-04

```text
latest DB insert == latest physical state
```

False under delayed replay.

## AP-05

```text
random timestamp as idempotency key
```

Weak.

## AP-06

```text
model score directly writes GPIO
```

Forbidden.

## AP-07

```text
network lost → control stops
```

Forbidden.

## AP-08

```text
old retained command controls device after reconnect
```

Forbidden.

## AP-09

```text
PZEM missing → assume current from command
```

False.

## AP-10

```text
dashboard screenshot = evidence
```

Insufficient.

---

# 101. Contract-first integration order

Recommended:

```text
1. hardware/physical contract stable
2. firmware local acquisition
3. device identity + telemetry schema
4. broker semantics
5. raw ingestion
6. normalized state/twin
7. command/ACK with actuator disabled
8. Controller A + SAFE_LOCAL
9. physical command verification
10. experiment metadata/export
11. XGBoost offline
12. inference integration
13. shadow predictive mode
14. Controller B
15. resilience/security hardening
16. final A/B campaign
```

---

# 102. Release gates inherited from Docs 00–01

## Gate A dependency

No AIoT closed-loop work can claim physical validity before hardware characterization.

## Gate B

Data path must preserve provenance/identity.

## Gate C

Prediction must be leakage-safe.

## Gate D

Command/control must pass safety and response verification.

## Gate E

Final campaign uses frozen versions.

---

# 103. Integration contract with Member A

Member A supplies:

```text
sensor identities
physical quality
hardware_config_id
calibration_id
PZEM semantics
applied actuator state
safe local firmware behavior
healthy electrical/thermal envelopes
```

Backend must not invent them.

---

# 104. Integration contract with Member B

Member B supplies:

```text
feature_version
model_version
horizon
risk semantics
calibration semantics
model artifact
evaluation constraints
```

Backend provides:

```text
versioned raw/normalized data
run manifests
online feature input
prediction audit
```

---

# 105. Integration contract with Member D

Member D supplies:

```text
policy_version
controller state machine
thresholds/persistence
freshness rules
reason codes
SAFE_LOCAL exit criteria
diagnosis rules
```

Backend/firmware enforce appropriate portions.

---

# 106. Repository spine implied by Doc 02

Conceptual:

```text
firmware/
  components/
    sensors/
    electrical/
    actuation/
    safety/
    telemetry/
    mqtt/
    config/

backend/
  app/
    ingestion/
    twin/
    experiments/
    prediction/
    policy/
    commands/
    api/
    observability/

ml/
  features/
  train/
  evaluate/
  artifacts/

infra/
  mosquitto/
  postgres/
  compose/

contracts/
  telemetry/
  command/
  ack/
  events/

experiments/
  manifests/
  exports/

evidence/
```

Exact directory names may vary.

Boundaries should remain recognizable.

---

# 107. Contract artifact recommendation

Although this document is normative prose, implementation should mirror key message structures in machine-readable schemas where practical:

```text
telemetry schema
event schema
command schema
ack schema
```

This is not a separate project-doc requirement.

It is executable validation.

---

# 108. JSON numeric semantics

Use JSON numbers for physical quantities with documented units.

Do not encode:

```text
"7.4 C"
```

inside numeric field.

Use:

```json
"t1_c": 7.4
```

---

# 109. Null/missing semantics

Differentiate:

```text
field absent
field null
quality invalid
value = 0
```

Current 0 A is a valid physical observation.

It is not “missing.”

---

# 110. Boolean versus enum

Door:

prefer:

```text
OPEN/CLOSED/UNKNOWN
```

rather than raw true/false with ambiguous polarity.

Cooling:

```text
OFF/ON
```

plus duty if needed.

---

# 111. Schema validation layers

## Syntax

JSON shape/type.

## Semantic

Examples:

- RH plausible;
- duty range;
- device ID matches topic;
- run ID format known;
- command expiry valid.

## Physical quality

Doc 01.

All three are distinct.

---

# 112. Experiment namespace

Suggested IDs:

```text
CG-S1-A-001
CG-S2-A-001
CG-S2-B-001
```

where semantics are defined by Doc 03.

Do not derive analysis solely from naming strings; keep explicit fields.

---

# 113. Pairing

Store:

```text
pair_id
```

separately.

Allows randomized order without string parsing.

---

# 114. Feature caching

Feature windows may be materialized/cache for performance.

Raw data remains authority.

Feature cache includes version.

---

# 115. Prediction persistence

Persist every report-grade prediction used in experiment analysis.

Do not recompute later with a changed model and pretend it was the online prediction.

---

# 116. Policy persistence

Persist decision:

- input prediction/state reference;
- output action;
- reason;
- policy version.

---

# 117. Command persistence

Persist before/around publish such that final audit can distinguish:

- created but not published;
- published;
- accepted;
- verified.

---

# 118. Physical verification persistence

Store:

```text
command_id
verification_type
window
result
evidence sample references
computed_at
algorithm/policy version
```

---

# 119. Incident model

A physical/control incident:

```text
incident_id
type
severity
start
end
device
run
related command
related evidence
status
notes
```

Examples:

- electrical response missing;
- unexpected OFF current;
- sensor degradation;
- SAFE_LOCAL event.

---

# 120. Security event model

Examples:

```text
AUTH_FAILED
ACL_DENIED
COMMAND_UNAUTHORIZED
COMMAND_EXPIRED
COMMAND_REPLAY_REJECTED
SCHEMA_REJECTED
```

Do not log secrets.

---

# 121. Data volume recalculation for new testbed

Old 20 L / 45-minute assumptions are not authoritative.

New 6 L planning envelope may use:

```text
48–64 independent valid runs
15–30 min/run
```

until pilot variance/dynamics freeze final campaign.

At 1 Hz:

### 48 × 20 min

\[
48\times1200=57{,}600
\]

rows.

### 64 × 20 min

\[
64\times1200=76{,}800
\]

rows.

### 64 × 30 min

\[
64\times1800=115{,}200
\]

rows.

This remains a small dataset operationally.

The important `n` for inference remains independent runs/events.

---

# 122. Model serving throughput

At 1 Hz one device:

```text
≈1 inference/sec
```

Even CPU XGBoost is sufficient.

GPU serving is not justified.

---

# 123. Security hardening ordering

Core:

```text
identity
TLS
ACL
authz
freshness
idempotency
audit
```

Conditional:

```text
mTLS
Secure Boot v2
Flash Encryption
signed OTA
```

Do not enable irreversible eFuse security in the final week without a validated recovery/flashing plan.

---

# 124. OTA policy

OTA is not P0 required.

If added:

- signed artifact;
- version;
- rollback/recovery;
- update audit.

Do not add OTA merely for feature count.

---

# 125. Device configuration updates

Remote configuration that changes control behavior is security-sensitive.

P0 can avoid dynamic remote config by using versioned firmware/config and backend policy.

If remote config exists:

- authz;
- version;
- bounds;
- audit.

---

# 126. Backend framework decision rationale

A Python/FastAPI-class baseline has high ROI because:

- API layer and XGBoost runtime share ecosystem;
- low request throughput;
- async broker/database integrations available;
- straightforward typed validation.

The architecture does not depend on a specific framework feature for safety.

---

# 127. Broker decision rationale

Mosquitto instead of a larger broker platform because:

- one/few clients;
- standard MQTT behavior;
- TLS/auth/ACL;
- reproducible config;
- small maintenance burden.

Do not add clustered broker HA as core.

---

# 128. Database decision rationale

PostgreSQL/Timescale instead of Influx + PostgreSQL because:

- one technology can cover both experiment relations and telemetry;
- SQL joins across run/prediction/command/evidence are valuable;
- project volume is small.

---

# 129. Observability decision rationale

OpenTelemetry-style traces/metrics are useful for:

- command path;
- backend latency;
- failure reconstruction.

But experiment correctness depends on:

- physical data;
- persistent audit;
- run manifests.

A trace being missing must not break control/recovery.

---

# 130. Recovery narrative

The canonical resilience story:

```text
normal online predictive mode
→ broker/network lost
→ device detects loss
→ SAFE_LOCAL
→ local reactive control continues
→ telemetry buffered if possible
→ connectivity returns
→ MQTT reconnect
→ reported state republished
→ backend reconciles boot/seq/twin
→ stale desired commands expire
→ AI/model health checked
→ return to online predictive mode
```

---

# 131. Final engineering acceptance

Doc 02 is implemented correctly when the team can demonstrate:

1. one primary ESP32 boots default-off;
2. telemetry carries stable device/boot/sequence identity;
3. QoS 1 duplicates do not create duplicate samples/effects;
4. raw telemetry remains immutable/replayable;
5. desired/reported/derived twin state remains separated;
6. command is non-retained, expiring and idempotent;
7. device can reject stale/invalid command;
8. Controller A works without cloud AI;
9. SAFE_LOCAL survives network/backend loss;
10. predictive inference is versioned and advisory;
11. Controller B passes through policy/safety gate;
12. ACK, electrical response and thermal response are separately recorded;
13. reconnect does not reapply stale intent;
14. final A/B run can be reconstructed end to end from stored evidence.

---

# 132. Reference sources

## MQTT / Edge

**[R1] OASIS — MQTT Version 5.0.**  
QoS 0/1/2, retained messages, Session Expiry, Message Expiry and protocol semantics.  
https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html

**[R2] Espressif — ESP-MQTT / ESP-IDF Programming Guide.**  
MQTT v5.0 and MQTT-over-TLS client support/examples.  
https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/protocols/mqtt.html

**[R3] Eclipse Mosquitto — mosquitto.conf / TLS documentation.**  
Authentication, ACL/dynamic security and TLS listener configuration.  
https://mosquitto.org/man/mosquitto-conf-5.html  
https://mosquitto.org/man/mosquitto-tls-7.html

## Twin / persistence

**[R4] AWS IoT Core — Device Shadow documents.**  
Desired/reported/delta/version reference semantics.  
https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-document.html

**[R5] PostgreSQL 18 Documentation — Concurrency Control / Transaction Processing.**  
Local transactional integrity and concurrency semantics.  
https://www.postgresql.org/docs/current/mvcc.html  
https://www.postgresql.org/docs/current/transactions.html

**[R6] Timescale Documentation — Hypertables and retention/continuous aggregates.**  
Time-series hypertable model and retention behavior.  
https://docs.timescale.com/

## ML

**[R7] XGBoost — Introduction to Model IO.**  
Stable model serialization versus unstable memory snapshots/pickle.  
https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html

**[R8] XGBoost — Prediction documentation.**  
DMatrix/in-place prediction semantics.  
https://xgboost.readthedocs.io/en/stable/prediction.html

## Observability / security

**[R9] OpenTelemetry — Messaging semantic conventions.**  
Messaging spans/metrics conventions; current messaging conventions remain under active stability evolution.  
https://opentelemetry.io/docs/specs/semconv/messaging/

**[R10] NIST IR 8259 Rev. 1 (2026).**  
IoT product cybersecurity risk-management foundation.  
https://csrc.nist.gov/pubs/ir/8259/r1/final

**[R11] NIST IR 8259A.**  
IoT Device Cybersecurity Capability Core Baseline.  
https://csrc.nist.gov/pubs/ir/8259/a/final

---

# 133. Freeze checklist

## Device

- [ ] one primary S3R2 only;
- [ ] boot default OFF;
- [ ] stable boot_id + seq;
- [ ] 1 Hz coherent snapshot;
- [ ] local SAFE_LOCAL independent of broker;
- [ ] PZEM timeout cannot block local safety.

## MQTT

- [ ] MQTT 5 baseline;
- [ ] telemetry/event/state/command/ack/health namespace;
- [ ] command `retain=false`;
- [ ] QoS 1 duplicate handled;
- [ ] session/expiry policy documented;
- [ ] TLS profile;
- [ ] topic ACL.

## Storage

- [ ] raw immutable;
- [ ] normalized new single cooling branch;
- [ ] no `current_1/current_2` legacy fields;
- [ ] run/version provenance;
- [ ] raw retained through project.

## Twin

- [ ] `reported`;
- [ ] `desired`;
- [ ] `derived`;
- [ ] no desired→reported overwrite;
- [ ] stale replay cannot regress current state.

## AI

- [ ] XGBoost core;
- [ ] model artifact version/hash;
- [ ] feature version;
- [ ] horizon explicit;
- [ ] score vs calibrated probability explicit;
- [ ] AI unavailable fallback.

## Control

- [ ] Controller A;
- [ ] Controller B;
- [ ] safety hierarchy;
- [ ] command ID/TTL/idempotency;
- [ ] ACK distinct from physical verify;
- [ ] electrical verify;
- [ ] thermal verify;
- [ ] SAFE_LOCAL/reconnect.

## Security

- [ ] device identity;
- [ ] TLS;
- [ ] ACL;
- [ ] backend authz for command;
- [ ] replay/stale rejection;
- [ ] secrets outside public source.

---

# 134. North star

> **Every ColdGuard software component should be able to answer one precise question: which physical or logical fact does it own, what identity and freshness make that fact current, what happens if the network repeats or delays it, and which evidence proves the next state rather than merely assuming it.**

> **The final closed loop is correct only when predictive intent remains subordinate to deterministic safety and the stored system trace can connect one physical trajectory to one prediction, one policy decision, one expiring command, one device-side application, one electrical response and one thermal outcome.**
