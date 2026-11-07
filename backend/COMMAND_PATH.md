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

Implemented in `command_store.ALLOWED_TRANSITIONS`. W06 software only ever
drives the non-physical states; the physical verification states are defined
but never set from software mocks.

| From | Allowed to |
|---|---|
| `CREATED` | VALIDATED, PUBLISHED, EXPIRED, UNKNOWN, PUBLISH_FAILED |
| `VALIDATED` | PUBLISHED, EXPIRED, UNKNOWN, PUBLISH_FAILED |
| `PUBLISHED` | ACK_ACCEPTED, ACK_REJECTED, EXPIRED, UNKNOWN |
| `UNKNOWN` | PUBLISHED, ACK_ACCEPTED, ACK_REJECTED, EXPIRED |
| `PUBLISH_FAILED` | PUBLISHED, EXPIRED, UNKNOWN |
| `ACK_ACCEPTED` | EXECUTED, ELECTRICAL_VERIFIED, THERMAL_VERIFIED, VERIFIED, FAILED_VERIFICATION *(reserved physical stages)* |
| `ACK_REJECTED` | *(terminal)* |
| `EXPIRED` | *(terminal — never executable again)* |
| `EXECUTED` | ELECTRICAL_VERIFIED, FAILED_VERIFICATION |
| `ELECTRICAL_VERIFIED` | THERMAL_VERIFIED, FAILED_VERIFICATION |
| `THERMAL_VERIFIED` | VERIFIED, FAILED_VERIFICATION |
| `VERIFIED` | *(terminal)* |
| `FAILED_VERIFICATION` | *(terminal)* |

Hard rules enforced by the matrix and row-locked compare-and-swap:

- A broker PUBACK sets `PUBLISHED`, never `ACK_ACCEPTED`.
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

## Publish workflow and crash windows

`CommandPublisher.publish` is three phase:

1. **Fence (DB txn).** `begin_publish_attempt` locks the command row, refuses
   expired commands (→ `EXPIRED`), refuses non-publishable states, fences
   concurrent publishers via an existing `PENDING` attempt, and records a new
   `PENDING` attempt. Commits before any broker traffic.
2. **Publish (broker).** Send QoS 1 / retain=false; wait for the broker PUBACK.
   A PUBACK proves broker acceptance only.
3. **Record (DB txn).** `finish_publish_attempt` persists the outcome:
   `PUBACK` → `PUBLISHED`, definite failure → `PUBLISH_FAILED`,
   timeout/ambiguous → `UNKNOWN`.

Crash window: a crash after phase 1 but before phase 3 leaves a `PENDING`
attempt and a non-settled command. `reconcile_pending_attempts` resolves these
to `UNKNOWN` on recovery and **never auto-replays** them. An operator retry
reuses the same `command_id`, re-checks expiry, and allocates a new attempt
number. A reconnect therefore cannot resend an expired command nor silently
re-actuate. The device's own idempotency memory is volatile (A-W06 handoff §3),
so the backend does not rely on it for cross-reboot safety.

## ACK arbitration

`record_ack` always appends receipt evidence, then for a schema-valid,
topic-agreeing ACK:

- unknown `command_id` → `UNMATCHED` (quarantined, no transition);
- ACK device ≠ command device → `CONFLICT` (no transition);
- command past expiry and not already accepted/rejected → command becomes
  `EXPIRED`, ACK retained as `LATE` (no resurrection);
- already settled with the same effective verdict → `DUPLICATE` (no second
  transition); different verdict → `CONFLICT` (settled verdict preserved);
- otherwise → matrix-checked transition to `ACK_ACCEPTED`/`ACK_REJECTED`/
  `EXPIRED`.

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