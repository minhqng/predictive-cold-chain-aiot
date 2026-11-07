# COLDGUARD — HỆ THỐNG BẢO VỆ CHUỖI LẠNH CHỦ ĐỘNG
## Member C Execution Playbook · IoT Backend · MQTT · Digital Twin · Persistence · Observability

> **Document:** `docs/05C-member-c-iot-backend-digital-twin.md`  
> **Course:** Internet of Things (IoT) — Course Project / Bài tập lớn  
> **Project:** **ColdGuard — Hệ thống bảo vệ chuỗi lạnh chủ động**  
> **Role:** **Member C — IoT Backend & Digital Twin**  
> **Planning horizon:** **24 weeks**  
> **Planned focused effort:** **279 hours**  
> **Average:** **11.6 h/week**  
> **Parents:**  
> `00-project-scope-architecture.md`  
> `01-physical-measurement-correctness-contract.md`  
> `02-aiot-closed-loop-engineering.md`  
> `03-verification-experiments-demo.md`  
> `04-team-execution-plan.md`  
> **Sibling playbooks:** `05A`, `05B`, `05D`  
> **Normative role:** chronological execution contract for Member C. This document converts the team-level IoT/backend/twin responsibilities into weekly issue packs, implementation artifacts, test/evidence obligations, handoffs and leader-review checkpoints.  
> **Non-authority rule:** this playbook MUST NOT redefine physical authority, model semantics, control safety hierarchy, experiment validity or statistical meaning. If this file conflicts with Docs 00–04, the parent document wins.  
> **Backend principle:** the backend is **not** the authority for physical truth. It preserves, validates, versions, reconciles and exposes physical/device state without collapsing `desired`, `reported`, `derived` or `verified` into one field.  
> **Messaging principle:** MQTT transport guarantees are not business-effect guarantees. `QoS 1` permits duplicate delivery; command correctness therefore depends on stable identity, expiry, idempotency, reconciliation and physical verification.  
> **Primary mission:** make every ColdGuard sample, event, prediction, command, ACK and physical verification state **traceable, durable, queryable, replay-safe, auditable and reproducible** from device to final experiment evidence.

> **Member C north star.**  
> **The backend succeeds when nobody has to infer what happened from the latest dashboard value. Every important state must be reconstructable from immutable evidence, stable identities, versioned configuration and explicit state transitions.**

---

# 0. How to use this playbook

Each week ends with:

```text
implementation
+
integration proof
+
data/state invariant proof
+
evidence artifact
+
handoff
```

Member C sits in the middle of the project’s dependency graph:

```text
A produces physical truth
        ↓
C preserves and transports it
        ↓
B learns from it
        ↓
D decides from it
        ↓
C persists/dispatches action
        ↓
A executes physically
        ↓
C records response
```

If C collapses semantics, downstream evidence becomes ambiguous.

---

# 1. Role contract

## 1.1 Member C owns

### Messaging

- Mosquitto baseline;
- MQTT 5 profile;
- TLS-capable configuration;
- authentication;
- topic ACL;
- topic namespace;
- telemetry/event/state/command/ACK/health routing;
- duplicate/reconnect behavior.

### Ingestion

- schema validation;
- semantic validation;
- raw immutable capture;
- normalized projection;
- deduplication;
- out-of-order handling;
- rejected-message evidence.

### Persistence

- PostgreSQL;
- TimescaleDB hypertable where useful;
- migrations;
- run metadata;
- command/prediction/event/audit tables;
- backup/restore.

### Digital Twin

- `reported`;
- `desired`;
- `derived`;
- twin version;
- sequence/freshness guards;
- reconnect reconciliation.

### Backend application

- modular monolith;
- API;
- realtime UI feed;
- command lifecycle persistence;
- inference adapter/integration;
- experiment export;
- observability;
- deployment reproducibility.

---

## 1.2 Member C does not own

C must not independently redefine:

```text
what T1 means
what counts as healthy current
what critical temperature means
which XGBoost threshold is valid
when Controller B is safe
which A/B pair is valid
```

C stores and enforces supplied contracts.

---

# 2. Technology baseline

## 2.1 Broker

Baseline:

```text
Eclipse Mosquitto
MQTT 5-capable
TLS
authentication
topic ACL
```

Reason:

- small deployment;
- standards-oriented;
- reproducible;
- supports authentication/TLS/ACL without cluster complexity.

---

## 2.2 Backend

Preferred:

```text
Python
FastAPI-class async API
modular monolith
```

Exact version pinned in repo.

One backend application is enough for:

- ingestion;
- twin;
- experiments;
- commands;
- API;
- prediction adapter.

Do not split into microservices merely to increase component count.

---

## 2.3 Database

Baseline:

```text
PostgreSQL
+
TimescaleDB
```

Use PostgreSQL relational integrity for:

- runs;
- commands;
- predictions;
- audit;
- model/policy metadata.

Use Timescale hypertable for:

- normalized telemetry.

---

## 2.4 Realtime

P0:

```text
WebSocket
or
SSE
```

for dashboard updates.

The frontend is a projection.

It is not authoritative state.

---

## 2.5 Deployment

Recommended:

```text
docker compose
├─ mosquitto
├─ postgres-timescale
├─ backend
└─ optional frontend
```

No Kubernetes.

---

# 3. Core engineering facts Member C must know

## 3.1 MQTT QoS

MQTT 5 defines:

```text
QoS 0 = at most once
QoS 1 = at least once
QoS 2 = exactly once at MQTT protocol delivery level
```

Therefore:

> QoS 1 duplicate delivery is normal behavior.

Application dedup remains mandatory.

---

## 3.2 Retained message

A retained MQTT message is stored by the broker for future subscribers.

Therefore:

```text
state/health may be retained
command must not be retained
```

A retained stale command after reconnect is unsafe.

---

## 3.3 Session expiry

MQTT 5 Session Expiry controls how long session state survives after disconnect.

This can support intermittent devices.

It does not replace database history.

---

## 3.4 Message expiry

MQTT 5 Message Expiry can limit broker-side lifetime.

ColdGuard still keeps payload-level:

```text
expires_at
```

because physical command validity is an application semantic.

---

## 3.5 Twin desired/reported split

A well-established IoT pattern distinguishes:

```text
desired
reported
```

and uses versioning to avoid stale updates.

ColdGuard adds:

```text
derived
```

for computed risk/quality/state.

---

## 3.6 PostgreSQL uniqueness

A composite unique constraint can enforce:

```text
(device_id, boot_id, seq)
```

for telemetry identity.

`INSERT ... ON CONFLICT` can make ingestion idempotent at persistence boundary.

---

## 3.7 MVCC

PostgreSQL uses MVCC.

This gives concurrent readers/writers consistent transaction snapshots.

Do not infer that all application-level invariants are automatic.

Cross-row/business consistency may still require careful transactions.

---

## 3.8 Timescale hypertable

A hypertable remains conceptually a PostgreSQL table partitioned into time-based chunks.

Use it because telemetry is naturally time-series.

Do not use it as an excuse to delete raw evidence.

---

# 4. Canonical message identity

## 4.1 Telemetry identity

```text
device_id
boot_id
seq
```

Unique tuple:

```text
(device_id, boot_id, seq)
```

---

## 4.2 Why not timestamp

Timestamp may:

- collide;
- drift;
- change after NTP;
- be rounded;
- arrive late.

It is event time, not unique identity.

---

## 4.3 Event identity

```text
event_id
```

globally unique.

---

## 4.4 Command identity

```text
command_id
```

stable across transport retry.

Do not generate a new ID merely because MQTT publish is retried.

---

# 5. Topic contract

Core namespace:

```text
coldguard/{device_id}/telemetry
coldguard/{device_id}/event
coldguard/{device_id}/state
coldguard/{device_id}/command
coldguard/{device_id}/command_ack
coldguard/{device_id}/health
```

---

# 6. QoS / retain matrix

| Topic | QoS | Retain |
|---|---:|---:|
| telemetry | 1 | no |
| event | 1 | no |
| state | 1 | yes if current-state projection |
| command | 1 | **no** |
| command_ack | 1 | no |
| health | 1 | yes |

---

# 7. Topic ownership

## Device publishes

```text
telemetry
event
state
command_ack
health
```

## Device subscribes

```text
command
```

## Backend publishes

```text
command
```

Backend/frontend does not publish raw device telemetry pretending to be device truth.

---

# 8. Broker security baseline

At minimum:

```text
listener
TLS
authn
ACL
anonymous disabled on secure listener
scoped topic access
```

Per-device principle:

```text
device-coldguard-001
can publish only own telemetry/event/state/ack/health
can subscribe only own command
```

---

# 9. Schema families

Machine-readable schemas should exist for:

```text
telemetry
event
state
command
command_ack
health
```

A schema version is not optional metadata.

Unknown incompatible schema:

```text
reject/quarantine
```

not “best effort”.

---

# 10. Raw evidence principle

Before normalization loses information:

```text
raw message
+
topic
+
received_at
+
validation result
```

must remain available.

The raw layer protects against later parser/feature bugs.

---

# 11. Normalized telemetry contract

Core normalized fields include:

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

---

# 12. Explicitly forbidden legacy fields

Do not rebuild old dual-channel schema:

```text
current_1
current_2
power_1
power_2
cmd_1
cmd_2
```

Current hardware has one cooling branch.

---

# 13. Table baseline

## 13.1 `telemetry_raw`

Purpose:

```text
immutable message evidence
```

---

## 13.2 `telemetry`

Purpose:

```text
normalized queryable time-series
```

Timescale hypertable candidate.

---

## 13.3 `events`

Purpose:

```text
meaningful state transitions / incidents / physical events
```

---

## 13.4 `device_twin`

Purpose:

```text
current projection
```

Not full history authority.

---

## 13.5 `commands`

Purpose:

```text
command lifecycle audit
```

---

## 13.6 `predictions`

Purpose:

```text
immutable inference records used by control/evaluation
```

---

## 13.7 `experiments`

Purpose:

```text
run metadata / validity / version provenance
```

---

## 13.8 `model_registry`

Purpose:

```text
artifact identity / feature/model provenance
```

---

# 14. Unique constraints

At minimum:

```text
telemetry:
UNIQUE(device_id, boot_id, seq)

commands:
PRIMARY KEY(command_id)

predictions:
PRIMARY KEY(prediction_id)

events:
PRIMARY KEY(event_id)

experiments:
PRIMARY KEY(run_id)
```

---

# 15. Ingestion transaction principle

For one telemetry message:

```text
validate
→ insert raw
→ insert normalized if valid
→ update current projection if newer
```

Use transactions where local atomicity matters.

Do not attempt ACID across:

```text
DB
MQTT
ESP32
physical TEC
```

---

# 16. Twin contract

## 16.1 Reported

Device/physical-owned projection.

Examples:

```text
sensor values
applied state
device mode
boot/seq
firmware
quality
```

---

## 16.2 Desired

Backend/policy intent.

Examples:

```text
requested cooling
command_id
expiry
```

---

## 16.3 Derived

Backend-computed:

```text
Tmean
gradient
slope
risk
cooling health
quality synthesis
```

---

## 16.4 No overwrite rule

Forbidden:

```text
desired ON
→ set reported ON
```

without device evidence.

---

# 17. Twin freshness

Current twin must consider:

```text
boot_id
seq
captured_at
quality
```

Late historical telemetry is stored but cannot blindly regress current state.

---

# 18. Twin version

Backend increments:

```text
twin_version
```

for projection changes.

Twin version is not a substitute for sensor sequence.

---

# 19. Reconnect reconciliation

On device reconnect:

1. accept current health/state;
2. identify current `boot_id`;
3. compare `seq`;
4. update reported;
5. mark expired desired commands;
6. reconcile unresolved commands;
7. allow prediction/control only when state is fresh enough.

---

# 20. Command lifecycle

Canonical backend states:

```text
CREATED
VALIDATED
PUBLISHED
ACK_ACCEPTED
EXECUTED
ELECTRICAL_VERIFIED
THERMAL_VERIFIED
VERIFIED
```

Alternates:

```text
ACK_REJECTED
EXPIRED
PUBLISH_FAILED
FAILED_ELECTRICAL
FAILED_THERMAL
UNKNOWN
```

---

# 21. Command creation transaction

A command record should be durable before/around publish.

Concept:

```text
transaction:
  insert command CREATED
  update desired twin intent

commit
publish MQTT
update PUBLISHED
```

Exact sequence may vary.

Audit must distinguish:

```text
created but never published
```

from:

```text
published
```

---

# 22. Command retry

Transport retry of the same logical command:

```text
same command_id
```

Only retry while still semantically fresh.

---

# 23. ACK processing

ACK updates protocol lifecycle.

It must not automatically set:

```text
VERIFIED
```

Physical verification requires downstream telemetry.

---

# 24. Unknown outcome

If publish occurs then connection breaks:

```text
outcome may be UNKNOWN
```

Reconcile from:

- later ACK;
- reported applied state;
- PZEM;
- thermal telemetry.

Do not assume:

```text
network failure = no actuation
```

---

# 25. Prediction persistence

Every control-relevant prediction stores:

```text
prediction_id
time
model_version
feature_version
horizon
risk_score
calibrated_probability?
input_window_start/end
feature quality
```

Never recompute later with a different model and pretend it was the online prediction.

---

# 26. Experiment provenance

Every final run must tie to:

```text
hardware_config_id
firmware_version
backend_version
schema_version
calibration_id
feature_version
model_version
policy_version
```

where applicable.

---

# 27. API baseline

Suggested:

```text
GET /api/devices
GET /api/devices/{id}/state
GET /api/devices/{id}/telemetry
GET /api/devices/{id}/events

GET /api/runs
GET /api/runs/{id}
GET /api/runs/{id}/telemetry
GET /api/runs/{id}/predictions
GET /api/runs/{id}/commands

GET /api/commands/{id}
GET /api/incidents
```

Manual command endpoint must route through D’s authorization/policy rules.

---

# 28. Realtime baseline

Dashboard needs around:

```text
~1 Hz
```

No reason to build high-frequency streaming infrastructure.

WebSocket is sufficient if used.

---

# 29. Observability

Metrics should cover:

```text
messages received
invalid messages
duplicate messages
out-of-order
ingest latency
DB errors
last telemetry age
prediction latency
command ACK latency
verification latency
SAFE_LOCAL events
```

---

# 30. OpenTelemetry stance

OpenTelemetry messaging semantic conventions are still evolving.

Therefore:

```text
run_id
command_id
prediction_id
boot_id
seq
```

remain durable business/evidence identifiers.

Tracing is supplementary.

---

# 31. Backup principle

Before final campaign:

- DB backup;
- restore proof;
- model artifacts;
- broker config;
- migration files;
- experiment export.

A backup that has never been restored is an unproven backup.

---

# 32. Raw-data retention

For project scale:

> keep all raw telemetry.

Do not auto-delete evidence to demonstrate a retention feature.

---

# 33. Export contract for Member B

Export must be deterministic and versioned.

Include:

```text
dataset_id
run IDs
query/version
checksum
hardware/config provenance
creation time
```

---

# 34. Member C Definition of Done

By W24 hand over:

```text
broker config
TLS/auth/ACL setup
schema artifacts
database migrations
raw ingestion
normalized telemetry
Timescale hypertable
twin
event/audit timeline
command lifecycle
replay/dedup logic
experiment API/export
prediction integration
observability
backup/restore
Docker Compose
clean deployment runbook
evidence index
```

---

# 35. Interfaces

## 35.1 A → C

A supplies:

```text
real telemetry schema
device identity
boot_id/seq
quality
hardware config
firmware version
applied state
ACK
```

---

## 35.2 C → A

C supplies:

```text
broker config
topic contract
command schema
device credential
integration fixtures
run metadata endpoint
```

---

## 35.3 B → C

B supplies:

```text
feature_version
model_version
artifact hash
horizon
risk semantics
input/output contract
```

---

## 35.4 C → B

C supplies:

```text
raw/normalized export
events
run manifests
checksums
prediction records
```

---

## 35.5 D → C

D supplies:

```text
policy version
controller state
command reason
TTL/freshness
authz rules
verification states
```

---

## 35.6 C → D

C supplies:

```text
fresh twin state
prediction record
durable command audit
ACK
physical verification events
reconnect state
```

---

# 36. Personal risk register

| Risk | Response |
|---|---|
| duplicate QoS1 telemetry | DB unique identity + `ON CONFLICT` |
| stale replay regresses twin | boot/seq freshness guard |
| retained command actuates after reconnect | command retain=false |
| raw data lost in parser bug | raw-first persistence |
| schema drift | schema_version |
| old two-channel schema leaks back | contract tests |
| command DB says success too early | lifecycle separation |
| ACK confused with physical verify | separate verification states |
| model prediction recomputed later | persist immutable prediction |
| DB outage during remote control | stop new durable remote commands |
| broker outage | SAFE_LOCAL, no HTTP bypass |
| too many services | modular monolith |
| excessive observability complexity | domain IDs first |
| backup untested | restore drill |
| current twin uses receive order only | seq/boot/event-time guard |
| secret committed | env/secrets excluded + test |
| anonymous broker | secure listener auth |
| ACL too broad | device-scoped topic rules |

---

# 37. Evidence convention

Recommended:

```text
evidence/C/Wxx/
```

Each README:

```text
goal
environment
versions
commands
test IDs
input fixture/run IDs
result
pass/fail
known limitation
```

---

# 38. Week 01 — Backend architecture, schema v0 and repo/bootstrap
**Effort:** **11 h**  
**Parent:** `04 W01`

## Objective

Create a backend skeleton that reflects the current one-branch architecture and can be reproduced from a clean machine.

---

## C-W01-01 — Architecture package map

Create module boundaries:

```text
ingestion
twin
experiments
prediction
policy adapter
commands
api
observability
```

One deployable app.

---

## C-W01-02 — Docker Compose skeleton

Services:

```text
mosquitto
postgres-timescale
backend
```

Optional frontend later.

---

## C-W01-03 — Schema fixture v0

Create valid sample:

```text
single cooling branch
T1/T2/T3
BME
door
PZEM
quality
device identity
```

No old dual-channel fields.

---

## C-W01-04 — Database migration baseline

Initialize migration framework.

Tables can be skeletal.

---

## C-W01-05 — Environment/config policy

Define:

```text
.env.example
no real secrets
dev/integration/experiment profiles
```

---

## Deliverables

```text
compose.yaml
backend skeleton
schema fixture v0
migration baseline
README bootstrap
```

---

## Pass criteria

Another member can run:

```text
docker compose up
```

and see broker, DB and backend healthy.

---

## Handoff

A receives topic/schema fixture.

B receives provisional data dictionary fields.

D receives backend module boundary.

---

# 39. Week 02 — Mosquitto, synthetic telemetry and raw persistence
**Effort:** **11 h**  
**Parent:** `04 W02`

## Objective

Prove a real MQTT→raw DB path before physical device integration.

---

## C-W02-01 — Broker config v0

Configure explicit listener.

Development secure baseline:

```text
anonymous disabled where practical
username/password or chosen auth
ACL skeleton
TLS-ready files/layout
```

---

## C-W02-02 — Synthetic device

Publish:

```text
telemetry
event
state
health
```

using final-ish topic namespace.

---

## C-W02-03 — MQTT consumer

Backend subscribes and records:

```text
topic
received_at
payload bytes/text
```

---

## C-W02-04 — `telemetry_raw`

Persist valid and invalid payloads with status.

---

## C-W02-05 — Integration proof

Publish 1000 synthetic messages.

Verify no unexplained loss at application level under local test.

---

## Deliverables

```text
mosquitto.conf
ACL v0
simulator
raw migration
1000-message test evidence
```

---

# 40. Week 03 — Validation, normalized telemetry and idempotent ingestion
**Effort:** **12 h**  
**Parent:** `04 W03`

## Objective

Make QoS 1 duplicate-safe and create a normalized data model.

---

## C-W03-01 — Schema validation

Reject:

- malformed JSON;
- missing identity;
- wrong type;
- unsupported schema.

---

## C-W03-02 — Topic/device identity validation

Payload `device_id` must agree with authorized/topic identity.

---

## C-W03-03 — Normalized table

Implement single cooling branch fields.

---

## C-W03-04 — Unique identity

Database:

```text
UNIQUE(device_id, boot_id, seq)
```

Use `ON CONFLICT` intentionally.

---

## C-W03-05 — Duplicate test

Inject same telemetry repeatedly.

Pass:

```text
raw handling visible
one normalized physical sample
duplicate metric/event
```

---

## C-W03-06 — Rejected-message path

Invalid input is visible and diagnosable.

---

# 41. Week 04 — Digital Twin v0 with real A telemetry
**Effort:** **10 h**  
**Parent:** `04 W04`

## Objective

Materialize real device state without collapsing desired/reported semantics.

---

## C-W04-01 — `device_twin`

Create:

```text
reported_state
desired_state
derived_state
twin_version
last_boot_id
last_seq
timestamps
```

---

## C-W04-02 — Reported updater

Only validated device observations update `reported`.

---

## C-W04-03 — Desired updater

Separate backend intent path.

No device evidence → no reported mutation.

---

## C-W04-04 — Freshness guard

Older seq/boot rules.

Test late old telemetry.

Revision `0004` leaves raw delivery evidence in its own transaction. The
normalized insert and reported Twin update commit together. Duplicate
deliveries keep the original normalized row and its admission decision.

Valid, topic-matched live telemetry can initialize reported state and advance
it by sequence within the current boot. Publishers of historical telemetry
must set the top-level boolean `replay: true`. The ingest path keeps replay,
synthetic, and retained deliveries in history and excludes them from reported
state. Repeated or non-boolean markers also keep a delivery out of reported
state. Broker authentication and topic ACLs establish publisher access. The
backend relies on the publisher to mark historical and synthetic data because
an absent marker on an authorized live topic is interpreted as live. Rows
from before revision `0004` lack an admission decision and remain history.

An unfamiliar boot stays in history until a trusted backend caller verifies
boot order independently and calls `reconcile_reported_boot` with the
expected current boot. This operation promotes the highest eligible sequence
from the verified boot and retires the previous one in the same transaction.
Receipt time, device time, and the boot ID string carry no boot-order authority.
Reconciliation is an internal database service. Caller authorization and
verification of successor chronology are the caller's responsibility.

The reported snapshot carries its normalized and raw row IDs and the original
event time. `last_reported_at` records when the database updated the projection.
Connectivity remains `UNKNOWN` until a separate connectivity policy establishes
it. Desired writes use the whole Twin version, with version zero reserved for
row creation. They store intent only.

---

## C-W04-05 — First real-device integration

A telemetry:

```text
ESP
→ Mosquitto
→ raw
→ normalized
→ reported twin
```

---

## Deliverables

```text
twin migration
twin service tests
real-device trace
```

---

# 42. Week 05 — Telemetry schema v1 and Timescale baseline
**Effort:** **13 h**  
**Parent:** `04 W05`

## Objective

Freeze the report-grade real telemetry path.

---

## C-W05-01 — Schema v1

Freeze compatible shape for W5–W8.

Include:

```text
device_id
boot_id
seq
captured_at
run_id
hardware_config_id
firmware_version
calibration_id
quality
```

---

## C-W05-02 — Timescale hypertable

Convert/create telemetry as hypertable where appropriate.

Test:

- insert;
- time-range query;
- run query.

---

## C-W05-03 — Raw/normalized reconciliation

For a sample run:

```text
raw count
normalized count
duplicates
invalids
```

must reconcile.

---

## C-W05-04 — Current-state API

Expose:

```text
GET device state
GET recent telemetry
```

---

## C-W05-05 — Timing metrics

Compute:

```text
backend_received_at - captured_at
```

only when clock quality permits.

Always expose receive time.

---

## Deliverables

```text
schema-v1
hypertable migration
reconciliation report
state API
```

---

# 43. Week 06 — Command lifecycle and ACK persistence
**Effort:** **13 h**  
**Parent:** `04 W06`

## Objective

Create a durable command path that never treats broker delivery as physical success.

---

## C-W06-01 — Command table

Fields include:

```text
command_id
device
created_at
expires_at
controller
policy
reason
action
status
```

---

## C-W06-02 — Publish service

Rules:

```text
QoS 1
retain=false
same command_id on retry
```

---

## C-W06-03 — ACK consumer

Persist:

```text
accepted/rejected
applied state
reason
ack time
```

---

## C-W06-04 — Lifecycle state machine

Support:

```text
CREATED
PUBLISHED
ACK_ACCEPTED
ACK_REJECTED
EXPIRED
UNKNOWN
```

and later physical verify states.

---

## C-W06-05 — Desired twin link

Desired stores current valid intent.

Expiry removes executable meaning.

---

## C-W06-06 — Integration with A/D

Run:

```text
legal
expired
duplicate
out-of-range
```

cases.

---

# 44. Week 07 — Experiment/run model and query/export v0
**Effort:** **12 h**  
**Parent:** `04 W07`

## Objective

Make physical runs first-class database objects.

---

## C-W07-01 — `experiments` table

Fields:

```text
run_id
scenario_id
controller_id
pair_id
versions
start/end
validity
notes
```

---

## C-W07-02 — Run lifecycle API

Support:

```text
PLANNED
ARMED
RUNNING
COMPLETED_RAW
VALID/INVALID/ABORTED
```

according to Doc 03.

---

## C-W07-03 — Telemetry→run association

Ensure run ID is explicit.

Do not infer only by timestamp.

---

## C-W07-04 — Export v0

Export run as:

```text
CSV/Parquet/JSON as chosen
+
manifest
```

---

## C-W07-05 — Event timeline

Join:

- door;
- command;
- ACK;
- telemetry state.

---

# 45. Week 08 — Platform soak, reconnect and backup baseline
**Effort:** **12 h**  
**Parent:** `04 W08`

## Objective

Prove the digital spine is stable enough for evidence collection.

---

## C-W08-01 — 1 Hz soak

Run with A:

```text
>=2 h
```

or evidence-justified duration.

Track:

- message count;
- duplicates;
- invalids;
- DB errors;
- gaps.

---

## C-W08-02 — Broker reconnect

Restart/drop broker.

Verify:

- device reconnect;
- current state resumes;
- no retained command.

---

## C-W08-03 — Backend restart

Restart backend.

Verify subscriptions/state recovery.

---

## C-W08-04 — Backup

Create database backup.

---

## C-W08-05 — Restore drill preliminary

Restore into clean DB and verify sample runs.

---

## C-W08-06 — Gate G2 platform report

GREEN/YELLOW/RED.

---

# 46. Week 09 — Reproducible dataset export and run integrity
**Effort:** **11 h**  
**Parent:** `04 W09`

## Objective

Give B a deterministic evidence export rather than ad hoc SQL.

---

## C-W09-01 — Export manifest

Include:

```text
dataset_id
run IDs
query/config version
created_at
backend commit
checksum
```

---

## C-W09-02 — Run integrity query

Automate:

- seq gaps;
- duplicates;
- time range;
- quality;
- version mismatch.

---

## C-W09-03 — S1 export

Export valid S1 baseline.

B can reproduce from command/script.

---

## C-W09-04 — API query stability

Run/test:

```text
run telemetry
events
commands
```

---

# 47. Week 10 — Event timeline and S2 support
**Effort:** **11 h**  
**Parent:** `04 W10`

## Objective

Make door-disturbance runs reconstructable from one timeline.

---

## C-W10-01 — Event model v1

Canonical event types:

```text
DOOR_OPENED
DOOR_CLOSED
COMMAND_CREATED
COMMAND_ACCEPTED
ELECTRICAL_VERIFIED
THERMAL_VERIFIED
```

plus fault/degraded later.

---

## C-W10-02 — Correlation

Persist:

```text
run_id
command_id
prediction_id
correlation_id
```

when available.

---

## C-W10-03 — S2 timeline endpoint/export

One query reconstructs:

```text
door
thermal
electrical
control
```

---

## C-W10-04 — Realtime timeline

UI can display event markers on telemetry chart.

---

# 48. Week 11 — Duplicate, out-of-order and offline replay
**Effort:** **12 h**  
**Parent:** `04 W11`

## Objective

Prove the backend remains correct when MQTT/network ordering is imperfect.

---

## C-W11-01 — Duplicate telemetry

Inject duplicates.

Assert normalized uniqueness.

---

## C-W11-02 — Out-of-order

Send seq:

```text
100
102
101
```

Store all historical valid records.

Current twin must not regress from 102 to 101.

---

## C-W11-03 — Old boot replay

Replay older boot session.

Historical DB accepts according to identity.

Current twin remains on active newer boot.

---

## C-W11-04 — Offline buffer replay

If A implements device buffering:

- receive delayed messages;
- preserve captured times;
- preserve seq;
- no current-state rollback.

---

## C-W11-05 — Metrics

Expose duplicate/out-of-order counters.

---

# 49. Week 12 — Backup/restore and baseline release candidate
**Effort:** **12 h**  
**Parent:** `04 W12`

## Objective

Close G3 digital evidence path.

---

## C-W12-01 — Clean restore

Restore:

- DB;
- run manifests;
- command audit.

---

## C-W12-02 — Migration-from-zero

Create clean database using migrations only.

No manual schema fix.

---

## C-W12-03 — Export reproducibility

Re-export same frozen run set.

Compare checksum/content semantics.

---

## C-W12-04 — Platform baseline tag

Tag/document release candidate.

---

## C-W12-05 — G3 evidence

Prove:

```text
raw retained
normalized correct
run export reproducible
backup restorable
```

---

# 50. Week 13 — Observability and latency instrumentation
**Effort:** **10 h**  
**Parent:** `04 W13`

## Objective

Measure the system latency components needed for AIW and reliability.

---

## C-W13-01 — Structured logs

Fields:

```text
device_id
run_id
boot_id
seq
command_id
prediction_id
event
reason
```

---

## C-W13-02 — Metrics

Implement key counters/histograms.

---

## C-W13-03 — Command timing

Persist/measure:

```text
created
published
ack
electrical verify
thermal verify
```

---

## C-W13-04 — Ingestion latency

Measure:

```text
received - captured
```

with clock-quality caveat.

---

## C-W13-05 — Tracing optional

Add OpenTelemetry only if low cost.

Durable business IDs remain primary.

---

# 51. Week 14 — Derived Twin and prediction provenance
**Effort:** **12 h**  
**Parent:** `04 W14`

## Objective

Integrate B’s feature/model metadata without making AI output physical truth.

---

## C-W14-01 — `predictions` table

Implement immutable prediction record.

---

## C-W14-02 — Derived twin risk

Current derived state includes:

```text
risk
horizon
model_version
feature_version
prediction age
```

---

## C-W14-03 — Provenance

Prediction links to:

- run;
- input window;
- model;
- feature.

---

## C-W14-04 — Stale prediction

Current projection excludes/marks stale predictions.

---

## C-W14-05 — API

Expose current and historical predictions.

---

# 52. Week 15 — Model artifact integration + broker/backend security
**Effort:** **12 h**  
**Parent:** `04 W15`

## Objective

Run the frozen-candidate XGBoost inference through the backend while enforcing real identity/ACL.

---

## C-W15-01 — Inference adapter

Load B’s official model artifact.

Verify:

```text
hash
model version
feature version
```

---

## C-W15-02 — Prediction persistence

Every report-grade inference is stored before/with policy use.

---

## C-W15-03 — Broker secure listener

Implement:

- TLS;
- authentication;
- device-scoped ACL.

---

## C-W15-04 — Backend authn/authz baseline

Protect command endpoint.

Frontend does not get direct broker command publish credentials.

---

## C-W15-05 — Negative ACL test with D

Unauthorized principal:

```text
publish command
```

must fail.

---

# 53. Week 16 — Outage / resynchronization readiness
**Effort:** **12 h**  
**Parent:** `04 W16`

## Objective

Prove reconnect semantics before Controller B physical enablement.

---

## C-W16-01 — Broker outage

Stop broker.

Observe:

- device offline status;
- no remote command;
- D/A SAFE_LOCAL.

---

## C-W16-02 — Backend outage

Broker remains.

Restart backend.

Verify:

- ingestion resumes;
- current state recovered;
- no stale desired auto-actuation.

---

## C-W16-03 — DB outage

Simulate DB unavailable.

Preferred:

```text
new predictive remote commands disabled
```

because durable audit cannot be guaranteed.

---

## C-W16-04 — Reconnect reconciliation

Check:

```text
boot
seq
desired expiry
pending commands
reported state
```

---

## C-W16-05 — G4 platform signoff

No Controller B until this is GREEN.

---

# 54. Week 17 — Shadow-mode full trace
**Effort:** **14 h**  
**Parent:** `04 W17`

## Objective

Trace the entire predictive path without physical predictive command.

---

## C-W17-01 — Online features/inference

Integrate B inference.

---

## C-W17-02 — Hypothetical policy event

Persist D’s shadow decision:

```text
would_command
reason
policy_version
```

but no command publication.

---

## C-W17-03 — Full trace query

One run reconstructs:

```text
telemetry
→ feature/prediction
→ shadow policy
→ Controller A actual command
→ physical response
```

---

## C-W17-04 — Online/offline comparison support

Give B exact prediction records.

---

## C-W17-05 — Audit UI

Show prediction and policy timing clearly.

---

# 55. Week 18 — Controller B command lifecycle integration
**Effort:** **14 h**  
**Parent:** `04 W18`

## Objective

Enable predictive command dispatch while preserving lifecycle/physical verification semantics.

---

## C-W18-01 — Controller B publish

Only after D approves policy.

---

## C-W18-02 — Command provenance

Link:

```text
prediction_id
policy_version
controller_id
run_id
```

---

## C-W18-03 — Verification states

Update command from telemetry-derived events:

```text
ELECTRICAL_VERIFIED
THERMAL_VERIFIED
VERIFIED / FAILED
```

Do not use ACK as shortcut.

---

## C-W18-04 — Failure window tests

Test at least:

- ACK lost;
- device reconnect;
- delayed telemetry.

Reconcile without duplicate actuation.

---

## C-W18-05 — Controller-B trace export

Generate proof artifact.

---

# 56. Week 19 — Final A/B campaign wave 1 data integrity
**Effort:** **14 h**  
**Parent:** `04 W19`

## Objective

Capture the first half of final campaign without data loss or semantic drift.

---

## C-W19-01 — Campaign namespace

Freeze:

- run IDs;
- pair IDs;
- version fields;
- controller IDs.

---

## C-W19-02 — Live integrity monitor

Monitor:

```text
last sample age
DB health
message errors
schema mismatch
```

Do not optimize model/policy.

---

## C-W19-03 — Per-run close

After each run:

- raw count;
- normalized count;
- sequence gap summary;
- event completeness.

---

## C-W19-04 — Backup wave 1

Snapshot/backup after campaign block.

---

## C-W19-05 — No silent repair

If a run has a missing critical window:

- mark issue;
- let Doc 03 validity rule decide.

Do not fabricate/interpolate source evidence.

---

# 57. Week 20 — Final A/B campaign wave 2 and evidence freeze
**Effort:** **13 h**  
**Parent:** `04 W20`

## Objective

Complete data capture and freeze the exact campaign dataset.

---

## C-W20-01 — Complete same integrity process

No schema migration during final campaign unless emergency correctness bug forces stop/restart.

---

## C-W20-02 — Final export

Create:

```text
final-campaign dataset ID
manifest
run list
checksums
```

---

## C-W20-03 — Evidence freeze

Backup:

- DB;
- exports;
- model metadata;
- policy metadata;
- broker/backend config.

---

## C-W20-04 — Trace spot-check

For representative A and B run:

reconstruct complete timeline.

---

## Gate contribution

G5 requires C's data-integrity signoff.

---

# 58. Week 21 — Resilience/security final campaign
**Effort:** **10 h**  
**Parent:** `04 W21`

## Objective

Close backend-side resilience/security proof after core A/B evidence is safe.

---

## C-W21-01 — Duplicate/out-of-order regression

Re-run production-like test.

---

## C-W21-02 — Broker/backend outage

Collect final evidence with D/A.

---

## C-W21-03 — ACL/auth test

Verify:

- unauthorized publish denied;
- legitimate device works.

---

## C-W21-04 — Backup/restore final

Restore final-ish data into clean environment.

---

## C-W21-05 — Incident/audit timeline

Ensure security/resilience events reconstructable.

---

# 59. Week 22 — Evidence integrity and final data package
**Effort:** **10 h**  
**Parent:** `04 W22`

## Objective

Make B’s final statistics and team defense reproducible from a frozen data package.

---

## C-W22-01 — Final integrity audit

Check:

- run count;
- pair IDs;
- versions;
- duplicate identities;
- sequence anomalies;
- invalid run records.

---

## C-W22-02 — Checksums

SHA-256 for:

- final export;
- manifests;
- model reference;
- key evidence tables.

---

## C-W22-03 — Export automation

Single command/script produces B-ready final dataset.

---

## C-W22-04 — Claim→evidence index support

Map command/resilience claims to DB/artifacts.

---

# 60. Week 23 — Deployment/runbook hardening
**Effort:** **10 h**  
**Parent:** `04 W23`

## Objective

Make digital infrastructure start reliably during demo/defense.

---

## C-W23-01 — Clean Compose deployment

From clean environment:

```text
clone
config secrets
compose up
migrate
health check
```

---

## C-W23-02 — Local demo profile

No public Internet required.

---

## C-W23-03 — Restore-ready snapshot

Prepare backup and restore instructions.

---

## C-W23-04 — Operational runbook

Include:

```text
start
stop
health
logs
broker auth
migration
backup
restore
reconnect troubleshooting
```

---

## C-W23-05 — Demo rehearsals

Own scenes:

- live twin;
- event timeline;
- command trace;
- reconnect.

---

# 61. Week 24 — Final digital handover
**Effort:** **8 h**  
**Parent:** `04 W24`

## Objective

No feature development.

Deliver a reproducible digital spine.

---

## C-W24-01 — Final migration-from-zero

Prove empty DB → current schema.

---

## C-W24-02 — Final backup/restore

Restore into clean database.

Verify:

- final runs;
- predictions;
- commands;
- events.

---

## C-W24-03 — Another member runs stack

C observes.

Undocumented manual fix = documentation defect.

---

## C-W24-04 — Final handover

Deliver:

```text
compose
broker config
TLS/auth/ACL instructions
migrations
schemas
API
twin semantics
backup/restore
observability
evidence export
runbook
```

---

# 62. Weekly effort summary

| Week | Hours | Primary emphasis |
|---:|---:|---|
| 01 | 11 | architecture/bootstrap |
| 02 | 11 | broker/raw ingestion |
| 03 | 12 | validation/dedup |
| 04 | 10 | twin v0 |
| 05 | 13 | schema v1/Timescale |
| 06 | 13 | command/ACK |
| 07 | 12 | experiment/run model |
| 08 | 12 | soak/reconnect/backup |
| 09 | 11 | deterministic export |
| 10 | 11 | event timeline |
| 11 | 12 | duplicate/order/replay |
| 12 | 12 | restore/release baseline |
| 13 | 10 | observability/latency |
| 14 | 12 | derived twin/predictions |
| 15 | 12 | model + security integration |
| 16 | 12 | outage/resync |
| 17 | 14 | shadow full trace |
| 18 | 14 | Controller B lifecycle |
| 19 | 14 | final A/B wave 1 |
| 20 | 13 | final A/B wave 2 |
| 21 | 10 | resilience/security |
| 22 | 10 | evidence integrity |
| 23 | 10 | deployment hardening |
| 24 | 8 | handover |
| **Total** | **279 h** | |

---

# 63. Member C gate responsibilities

## G0

- architecture skeleton;
- current one-branch schema.

## G1

- synthetic/real telemetry path;
- twin separation.

## G2

- stable raw/normalized ingestion;
- platform soak;
- backup baseline.

## G3

- deterministic experiment export;
- backup/restore;
- replay correctness.

## G4

- prediction integration;
- TLS/ACL;
- outage/reconnect;
- twin reconciliation.

## G5

- final A/B data integrity;
- frozen export/checksum;
- complete command traces.

## G6

- clean deploy;
- restore;
- reproducible handover.

---

# 64. Leader review rubric for Member C

Leader should ask:

## Identity

- what is unique?
- duplicate handling?

## State

- desired vs reported vs derived?
- can late message regress current state?

## Command

- retain?
- TTL?
- status?
- unknown outcome?

## Evidence

- raw preserved?
- run export reproducible?
- versions present?

## Failure

- broker down?
- backend down?
- DB down?
- reconnect?

## Security

- anonymous command possible?
- ACL scoped?
- frontend bypass?

## Reproducibility

- clean migration?
- backup restore?

---

# 65. Common failure patterns Member C must avoid

## 65.1 `QoS 1 = exactly once`

False.

---

## 65.2 Timestamp as unique identity

Weak.

Use device/boot/seq.

---

## 65.3 Retained command

Forbidden.

---

## 65.4 Desired overwrites reported

Forbidden.

---

## 65.5 Latest DB arrival = current physical state

False under replay/out-of-order.

---

## 65.6 ACK = physical success

False.

---

## 65.7 Dashboard = source of truth

False.

---

## 65.8 Delete raw to save space

Unnecessary and harmful at this scale.

---

## 65.9 Split backend into many services

Adds failure/ops cost without project value.

---

## 65.10 Direct frontend→broker control

Avoid.

Route through backend authz/policy/command audit.

---

## 65.11 Ignore DB outage but keep sending remote commands

Unsafe audit semantics.

---

## 65.12 Use OTel span IDs as experiment identity

Wrong.

Use durable domain IDs.

---

# 66. Canonical telemetry processing flow

```text
MQTT receive
→ topic/device auth context
→ raw persist
→ JSON/schema validation
→ semantic validation
→ dedup identity
→ normalized insert
→ event extraction
→ current twin update if newer
→ realtime projection
→ feature/prediction pipeline
```

---

# 67. Canonical command flow

```text
policy action
→ backend authz
→ command row
→ desired twin
→ MQTT publish non-retained
→ device ACK
→ reported applied state
→ PZEM response
→ thermal response
→ verification state
→ audit timeline
```

---

# 68. Canonical reconnect flow

```text
device offline
→ LWT/health
→ SAFE_LOCAL handled at device/D
→ device reconnect
→ current health/state
→ boot/seq reconciliation
→ old desired expiry
→ command reconciliation
→ fresh telemetry
→ prediction/control resume
```

---

# 69. Suggested SQL invariant examples

## Telemetry uniqueness

```sql
UNIQUE (device_id, boot_id, seq)
```

## Run identity

```sql
PRIMARY KEY (run_id)
```

## Command identity

```sql
PRIMARY KEY (command_id)
```

## Prediction identity

```sql
PRIMARY KEY (prediction_id)
```

Implementation syntax may vary.

---

# 70. Current-state update guard

Conceptual logic:

```text
if same boot:
    accept current projection only if seq newer

if new boot:
    switch active boot only with explicit reconnect/current-state logic

if old boot:
    store historically
    do not regress active projection
```

---

# 71. Raw versus normalized error handling

## Raw

Keep even when:

- schema invalid;
- unknown optional field;
- parse failure.

As long as storing payload is safe.

## Normalized

Only create when required semantics valid.

---

# 72. Migration discipline

Every schema change:

```text
migration file
up path
review
test from zero
```

Do not manually edit production/experiment DB schema.

---

# 73. Experiment DB freeze

During final A/B:

avoid migrations.

If emergency correctness migration needed:

- stop campaign;
- backup;
- migrate;
- version;
- review comparability;
- resume explicitly.

---

# 74. Security profile

## Development

May use local CA / dev credentials.

## Experiment/demo

Must use:

- authenticated device;
- non-anonymous command path;
- TLS-capable secure listener;
- scoped ACL.

---

# 75. Secret handling

Never commit:

```text
password
private key
real token
```

Use ignored secret files or environment injection.

Repository contains examples only.

---

# 76. Device principal mapping

Broker connection identity should authorize topic namespace.

Do not trust only payload:

```json
{"device_id":"coldguard-001"}
```

because payload is user-controlled input.

---

# 77. Audit event examples

```text
DEVICE_CONNECTED
DEVICE_DISCONNECTED
SCHEMA_REJECTED
DUPLICATE_TELEMETRY
OUT_OF_ORDER_TELEMETRY
COMMAND_CREATED
COMMAND_PUBLISHED
COMMAND_ACK_ACCEPTED
COMMAND_ACK_REJECTED
ELECTRICAL_VERIFIED
THERMAL_VERIFIED
COMMAND_VERIFICATION_FAILED
SAFE_LOCAL_ENTER
SAFE_LOCAL_EXIT
AUTH_FAILED
ACL_DENIED
```

---

# 78. API response semantics

Current state endpoint should include:

```text
value
quality
age/freshness
source boot/seq
```

A stale value without age is misleading.

---

# 79. Prediction API semantics

Expose:

```text
risk_score
probability only if calibrated
horizon
model_version
prediction_time
age
quality
```

---

# 80. Command API semantics

Expose:

```text
requested
applied
verification
status
reason
timestamps
```

Avoid a single `success=true`.

---

# 81. Incident timeline

A reviewer should be able to open one incident and see:

```text
physical state
prediction
policy
command
ACK
electrical response
thermal response
final classification
```

---

# 82. Backup contents

At minimum:

```text
PostgreSQL dump
migration files
model metadata reference
broker config
run/export manifests
```

Raw external file artifacts also backed up separately.

---

# 83. Export format

CSV is transparent.

Parquet is efficient.

Either can be valid.

If using Parquet:

- provide easy CSV/report route for graders if needed.

The critical requirement is deterministic schema/provenance.

---

# 84. Performance expectations

At approximately:

```text
1 telemetry msg/sec
```

Member C optimizes correctness, not throughput benchmarks.

Meaningful performance:

- no evidence loss;
- stable query;
- command latency small relative to thermal dynamics;
- reconnect predictable.

---

# 85. Soak acceptance

No arbitrary enterprise SLO required.

Evidence should show:

- sustained ingest;
- no growing unexplained errors;
- stable DB;
- no duplicate normalization;
- manageable resources.

---

# 86. OpenTelemetry caveat

Messaging semantic conventions are still development/evolving.

Therefore project correctness must not depend on a particular `messaging.*` attribute name.

---

# 87. FastAPI background-work caveat

Small in-process work is fine.

Do not put long-running critical experiment processing into fragile request-background callbacks if durability matters.

Durable evidence should be persisted.

---

# 88. Final Member C defense anchors

### Why MQTT?

> lightweight pub/sub fits IoT and supports explicit delivery/session semantics.

### Why QoS 1?

> practical at-least-once delivery; duplicate is handled by application identity.

### Why not QoS 2?

> transport exactly-once does not make physical actuation exactly-once or valid.

### Why not retained command?

> stale command could arrive after reconnect/subscription and actuate incorrectly.

### Why `boot_id + seq`?

> distinguishes reboot sessions and gives stable message order/identity independent of clock.

### Why raw table?

> allows later reprocessing/audit if parser or feature logic changes.

### Why Timescale?

> telemetry is time-series but still benefits from PostgreSQL/SQL and relational experiment joins.

### Why Twin?

> provides current synchronized representation while keeping desired/reported/derived authority separate.

### Why not frontend as authority?

> UI can lag or fail; database/device evidence determines state.

### Why modular monolith?

> one device and small workload; extra services create failure boundaries without research value.

---

# 89. Reference sources for Member C execution

**[R1] OASIS — MQTT Version 5.0.**  
Official standard covering QoS levels, retained messages, session state, Session Expiry and Message Expiry.  
https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html

**[R2] Eclipse Mosquitto — `mosquitto.conf` manual.**  
Authentication, ACL, listeners and certificate-based TLS configuration.  
https://mosquitto.org/man/mosquitto-conf-5.html

**[R3] Eclipse Mosquitto — Authentication methods.**  
Password-based and plugin/dynamic-security approaches.  
https://mosquitto.org/documentation/authentication-methods/

**[R4] AWS IoT Core — Device Shadow documents.**  
Reference semantics for `desired`, `reported`, metadata, version and stale/out-of-order handling. ColdGuard implements its own lightweight twin, not AWS IoT.  
https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-document.html

**[R5] PostgreSQL Documentation — Constraints / `UNIQUE`.**  
Composite uniqueness used for stable telemetry identity.  
https://www.postgresql.org/docs/current/ddl-constraints.html

**[R6] PostgreSQL Documentation — `INSERT ... ON CONFLICT`.**  
Idempotent insert/update behavior around unique constraints.  
https://www.postgresql.org/docs/current/sql-insert.html

**[R7] PostgreSQL Documentation — MVCC / concurrency control.**  
Transaction snapshots and concurrent read/write behavior.  
https://www.postgresql.org/docs/current/mvcc.html

**[R8] Timescale Documentation — Hypertables.**  
PostgreSQL time-series tables automatically partitioned into time-based chunks.  
https://docs.timescale.com/use-timescale/latest/hypertables/

**[R9] FastAPI — WebSockets.**  
Official WebSocket support for realtime application updates.  
https://fastapi.tiangolo.com/advanced/websockets/

**[R10] OpenTelemetry — Messaging semantic conventions.**  
Useful for tracing/metrics, while current messaging conventions are still documented with development/stability caveats.  
https://opentelemetry.io/docs/specs/semconv/messaging/

---

# 90. Final handover checklist

## Broker

- [ ] MQTT 5 profile.
- [ ] command retain=false.
- [ ] auth.
- [ ] ACL.
- [ ] TLS instructions.
- [ ] LWT/health behavior.

## Ingestion

- [ ] raw immutable.
- [ ] normalized schema.
- [ ] duplicate handling.
- [ ] out-of-order handling.
- [ ] rejected-message evidence.

## Database

- [ ] migrations.
- [ ] telemetry hypertable.
- [ ] events.
- [ ] commands.
- [ ] predictions.
- [ ] experiments.
- [ ] model registry.

## Twin

- [ ] reported.
- [ ] desired.
- [ ] derived.
- [ ] version.
- [ ] boot/seq freshness.
- [ ] reconnect reconciliation.

## Command

- [ ] durable command record.
- [ ] ACK.
- [ ] unknown outcome.
- [ ] electrical verify.
- [ ] thermal verify.
- [ ] audit.

## Experiment

- [ ] run API.
- [ ] deterministic export.
- [ ] manifest/checksum.
- [ ] final campaign freeze.

## Resilience

- [ ] broker outage.
- [ ] backend outage.
- [ ] DB outage behavior.
- [ ] replay.
- [ ] restore.

## Final

- [ ] Compose from clean environment.
- [ ] no committed secrets.
- [ ] operational runbook.
- [ ] another member can restore/run.
- [ ] evidence index complete.

---

# 91. North star

> **Member C succeeds when the complete ColdGuard history survives network duplication, delayed replay, backend restart and human inspection without changing its meaning.**

> **The twin is a projection, not reality. MQTT is transport, not correctness. The database is durable evidence, not physical authority.**

> **The strongest backend contribution is the ability to answer, for any final experiment: which physical sample arrived, which run it belonged to, which model saw it, which policy acted on it, which command was sent, what the device reported, what current actually flowed and what thermal response followed.**
