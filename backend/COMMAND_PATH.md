# ColdGuard backend command path (Member C W06)

Software implementation of the durable command lifecycle and ACK persistence.
This document describes the **software** command path only. It does **not**
claim physical actuation, electrical verification, thermal verification, or
real-device integration acceptance. Those remain externally gated (Member A
transport/clock, Member D authorization, physical evidence).

Canonical authority:

- `docs/02-aiot-closed-loop-engineering.md` §28–§35 (command contract,
  validation, idempotency, freshness, ACK, lifecycle, unknown outcome,
  physical verification), §7 (QoS/retain), §64 (ACK example).
- `docs/05C-member-c-iot-backend-digital-twin.md` §43 (C-W06-01…06), §16
  (reported/desired/derived separation).
- `evidence/A/W06/handoff-w06.md` and `evidence/A/W06/ack-fixture.json`
  (device verdict vocabulary and interpretability fields).

## Topics and transport

| Topic | Direction | QoS | Retain |
|---|---|---:|---:|
| `coldguard/{device_id}/command` | backend → device | 1 | **false** |
| `coldguard/{device_id}/command_ack` | device → backend | 1 | false |

Retained commands are forbidden (Doc 02 §31.2): a retained stale actuation is
unsafe. The publisher passes `qos=1, retain=False` explicitly and tests prove
both on the wire against a disposable Mosquitto, including that a late
subscriber receives no retained command.

The backend publishes the canonical Doc 02 §28.1 JSON envelope. The Member A
device consumes a flat `key=value` encoding with unit-explicit renames
(`created_at_ms`, `expires_at_ms`, `action_cooling`, `action_duty_permille`);
translating between these is the serial gateway's responsibility and is an open
contract item (A-W06 handoff §6.2), **not** implemented or claimed here.

## Lifecycle states and transition matrix

The ordinary transition API uses `command_store.ALLOWED_TRANSITIONS`. Physical
states remain readable in storage and have no protocol transition edges.

| From | Allowed to |
|---|---|
| `CREATED` | VALIDATED, PUBLISHED, EXPIRED, UNKNOWN, PUBLISH_FAILED |
| `VALIDATED` | PUBLISHED, EXPIRED, UNKNOWN, PUBLISH_FAILED |
| `PUBLISHED` | ACK_ACCEPTED, ACK_REJECTED, EXPIRED, UNKNOWN |
| `UNKNOWN` | PUBLISHED, ACK_ACCEPTED, ACK_REJECTED, EXPIRED |
| `PUBLISH_FAILED` | PUBLISHED, EXPIRED, UNKNOWN |
| `ACK_ACCEPTED` | *(settled protocol verdict)* |
| `ACK_REJECTED` | *(terminal)* |
| `EXPIRED` | *(terminal — never executable again)* |
| Physical verification states | *(reserved for an independent evidence authority)* |

Hard rules enforced by the matrix and row-locked compare-and-swap:

- A successful broker PUBACK records broker delivery and sets `PUBLISHED` if
  the command remains unsettled and fresh.
- A device `ACCEPTED` ACK sets `ACK_ACCEPTED`, never `VERIFIED`;
  `verification_status` stays `NONE`.
- An expired command can never return to a publishable state.
- A settled verdict (`ACK_ACCEPTED`/`ACK_REJECTED`/`EXPIRED`) is never
  regressed by a later ACK; a conflicting ACK is retained as evidence.

## Storage (revision 0008)

- `commands` — immutable `command_id` primary key; `expires_at > created_at`,
  duty range, action and status CHECK constraints; `payload_sha256` for
  conflict detection; `verification_status` defaults to `NONE`.
- `command_attempts` — append-only publish attempts (`PENDING`, `PUBACK`,
  `FAILED`, `TIMEOUT`, `UNKNOWN`), unique `(command_id, attempt_no)`.
- `command_acks` — append-only ACK receipts including unmatched, invalid,
  topic-mismatched, conflicting, duplicate and late evidence. No foreign key on
  `command_id`, so forged/unmatched ACKs remain observable.
- `command_transitions` — append-only lifecycle audit trail.

Downgrade to revision 0007 takes exclusive locks on the four command tables and
refuses to proceed if any holds evidence, including unmatched ACKs. An empty
command schema can downgrade while preserving W05 tables.

## Publish workflow and crash windows

`CommandPublisher.publish` is three phase:

1. **Fence (DB transaction).** Check desired ownership under the per-device
   advisory lock and reserve a `PENDING` attempt under the command row lock.
   Commit before any broker traffic.
2. **Dispatch (new DB transaction).** Reacquire the device lock, recheck
   ownership, expiry, and pending attempt, then send at QoS 1 with retain
   disabled. Supersession waits for this bounded handoff to finish. The command
   row stays unlocked during transport so ACK ingestion can commit independently.
3. **Record (same DB transaction as dispatch).** Persist the outcome:
   `PUBACK` → `PUBLISHED`, definite failure → `PUBLISH_FAILED`,
   timeout/ambiguous → `UNKNOWN`. A late PUBACK fills broker evidence without
   replacing a device verdict or reviving an expired command.

Crash window: a crash after phase 1 but before phase 3 leaves a `PENDING`
attempt and a non-settled command. `reconcile_pending_attempts` resolves these
to `UNKNOWN` on recovery and **never auto-replays** them. An operator retry
reuses the same `command_id`, re-checks expiry, and allocates a new attempt
number. Paho transport requires a dedicated MQTT 5 client constructed with
`reconnect_on_failure=False`. After ambiguous delivery it retires the client.
A deliberate retry after retirement uses a fresh client. The device must still
check the absolute expiry and deduplicate the stable ID. An already queued
packet can arrive after a newer intent commits or after the expiry check. The
database lock covers backend dispatch order and cannot revoke a broker packet.

## ACK arbitration

`record_ack` always appends receipt evidence, then for a schema-valid,
topic-agreeing ACK:

- unknown `command_id` → `UNMATCHED` (quarantined, no transition);
- ACK device ≠ command device → `CONFLICT` (no transition);
- command past expiry and not already accepted/rejected → command becomes
  `EXPIRED`, ACK retained as `LATE` (no resurrection);
- already settled with the same effective verdict → `DUPLICATE` (no second
  transition); different verdict → `CONFLICT` (settled verdict preserved);
- before a recorded PUBACK, a same-device ACK can settle a matching attempt
  whose dispatch may have reached the broker. A receipt without such an attempt
  is quarantined. The broker ACL supplies the authenticated device boundary.

`DUPLICATE_CANONICAL` uses `canonical_status` as the effective verdict.

## Desired Twin linkage (C-W06-05)

`command_service.create_command_intent` persists the command and links the
desired Twin in one transaction, serialized per device with a transaction-level
advisory lock and the existing optimistic compare-and-swap (`update_desired`).
Desired state points at the active command intent; reported and derived state
are never written by the command path (they remain the W04 empty-object default
until device observations arrive). `active_desired_intent` returns executable
meaning only while the command status is executable and unexpired; expired,
rejected and superseded commands lose executable meaning while remaining
auditable. An uncertain (`UNKNOWN`) publish is represented explicitly, never as
a fabricated device OFF/ON.

Replaying an existing command ID returns its stored record without changing
desired ownership. An intent that is already expired at creation is recorded
as expired and cannot displace the current desired command.

## ACK ingestion startup

Set `COLDGUARD_MQTT_ACK_INGEST=true` to start the ACK subscriber with the
backend lifespan. It defaults to disabled. Apply revision 0008 first and
provide the backend subscriber credentials. Startup waits for successful
subscription acknowledgement and fails visibly if database access, broker
authentication, or subscription readiness fails. Disconnect clears readiness.
The subscriber uses a dedicated MQTT client and disposes its database engine
on shutdown.

## Safety boundary

- Remote TEC actuation remains disabled by default; this slice provides the
  software path and tests it only against disposable providers.
- The Member A device rejects every command whose absolute expiry it cannot
  evaluate as `SAFETY_BLOCKED` / `EPOCH_UNSYNCHRONIZED` until its clock is
  synchronized (A-W06 handoff §1). The backend models this verdict but does not
  bypass it.
- No unauthenticated public HTTP endpoint publishes cooling commands; the
  publisher is an internal service invoked by trusted policy/test code.
- An ACK is protocol evidence, never proof of electrical or thermal action.

## Verification classification

- **UNIT:** contract validation, transition matrix, ACK classification.
- **REAL LOCAL PROVIDER:** PostgreSQL storage/constraints/concurrency,
  migration 0008 upgrade/populated/downgrade/re-upgrade, Mosquitto QoS1/retain
  publish, ACK consumer correlation, end-to-end intent→publish→ACK→desired.
- **PHYSICAL NOT AUTHORIZED:** real ESP32-S3 command delivery, electrical and
  thermal verification, Member D authorization, real-device acceptance.

## Controller B integration (W18, revision 0012)

`ControllerBDispatch` is a server-side software entrypoint, not an HTTP command
route. It is disabled unless the operator independently provisions both a
`DPolicyAuthority` for the approved policy and a trusted `FrozenModelSpec`.
Backend authentication and an explicit device allowlist remain required. An
HMAC-SHA-256 approval covers the **entire canonical command**, including run,
prediction, action, expiry and expected Twin version. No test key, generated
model reference or example signature constitutes real Member D approval.

Before creating intent, the dispatch path checks the running predictive run,
declared versions, current prediction, exact model/feature hashes and horizon,
active boot, measurement provenance, quality and acquisition freshness. Delayed
receipt must not renew an old acquisition's freshness budget. Intent creation
enforces the signed expected Twin version. The final dispatch transaction
rechecks and fences the prediction, run, Twin and linked measurements through
the bounded transport handoff. A newer report, replacement prediction, closed
run, superseding intent or expiry can revoke the reservation before sending.

Revision `0012` adds:

- `policy_approvals`: the provisioned-key fingerprint, exact command digest,
  signature digest, approved model specification and its digest, and approval
  receipt time. The receipt commits with the reserved attempt **before** any
  broker traffic. Keys and reusable signatures are not exported.
- `physical_assessments`: independently authenticated assessment evidence,
  scoped to a command/device/run, commissioned envelope and calibration, with
  acquisition windows, exact telemetry IDs and raw SHA-256 values.
- UPDATE guards for command provenance and both evidence tables, and the
  `EXECUTED` verification status. Downgrade refuses existing execution,
  assessment or approval evidence; it never deletes history to make rollback
  succeed.

Generic `CommandPublisher` calls cannot bypass predictive approval with an
arbitrary callback. A predictive `UNKNOWN` outcome requires investigation and
new authorized context; `ControllerBDispatch` refuses retry of that envelope.
Lost device ACK or subscriber reconnect does not make a published command
publishable again. Device-side deduplication, absolute expiry, SAFE_LOCAL and
physical safety remain Member A/D responsibilities; backend fencing is not an
exactly-once physical-actuation guarantee.

### Independent verification stages

The ordinary transition API and raw MQTT event receipts cannot certify physical
success. Only the separately provisioned `PhysicalAuthority` entrypoint may
record the following supported sequence:

```text
ACK_ACCEPTED → EXECUTED → ELECTRICAL_VERIFIED → THERMAL_VERIFIED → VERIFIED
                     \→ FAILED_VERIFICATION (from any supported assessment stage)
```

Assessment checks retain the accepted ACK's boot and chronology, exact raw
bytes/projection/normalized content and receipt/acquisition consistency,
commanded applied state, calibration and measurement scope. Thermal assessment
requires a trajectory, not a single sample. A trusted assessor owns the actual
electrical/thermal interpretation and commissioned thresholds; these storage
checks do not implement or certify those physical criteria. Generated fixtures,
even when deliberately PHYSICAL-labelled to attack a gate, prove software
authority plumbing only. ACK remains a protocol verdict and late ACKs cannot
regress the assessment chain.

### Trace query

`GET /api/runs/{run_id}/controller-b-trace` returns predictive commands with
prediction/input provenance, policy approval receipts, attempts, ACKs,
transitions and independent assessments for the exact run and device. It accepts
`limit` 1–25, bounded `offset`, and `download=true`. Repeating a page against an
unchanged database snapshot produces the same canonical JSON bytes; dynamic
prediction ages are excluded. Missing physical evidence is explicitly
`UNAVAILABLE`, not manufactured from delivery or reported ON/OFF state.

W18 tests cover exact signed envelopes, model/measurement rejection, final
revocation and lock contention on real PostgreSQL, migration preservation and
rollback refusal, and real loopback Mosquitto software-peer lost-ACK,
disconnect/reconnect and delayed-telemetry windows. Injected transport tests
are distinct from actual broker tests. All are standalone software evidence;
official B artifacts, A/D integration, commissioning and physical campaigns
remain external acceptance items.
