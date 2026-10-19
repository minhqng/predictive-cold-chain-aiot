# Command-validator contract (draft, W02/W03)

**Status:** draft v0 contract for the planned W03 pure-function implementation and command matrix. W04 owns the real command-v0 transport/actuator integration and may refine field names; any change must keep the check order and safety semantics below.
**Implementation target:** `control/src/coldguard_control/commands.py`
**Planned tests:** `control/tests/test_command_matrix.py`

## 1. Inputs

### 1.1 Command request (schema v1)

| Field | Type | Constraint | Reason |
|---|---|---|---|
| `schema_version` | integer | exactly `1` | Reject unknown semantics rather than guess |
| `command_id` | non-empty string | unique per logical command | Idempotency key |
| `device_id` | non-empty string | must equal the receiving device | Wrong-device protection |
| `action` | `ON` / `OFF` | legal action family | No reverse/PWM shortcut in v0 |
| `duty` | number or omitted | OFF: omitted or `0.0`; ON: `1.0`/omitted when PWM is disabled; characterized bounds when PWM is enabled | No invented duty semantics; matches v0 fixture `action.duty = 1.0` |
| `created_at` | finite number (epoch seconds) | not implausibly in the future | Clock/schema anomaly |
| `expires_at` | finite number | `> created_at`; `now < expires_at` | TTL |
| `authorized` | boolean | must be true | Authorization evidence from the authenticated path |
| `retain` | boolean | must be false | No retained/replayed command delivery |

`CommandRequest` deliberately does not carry MQTT topic, QoS, signature or
credentials: those belong to the transport/security layers. `authorized` is an
assertion, not a credential check (see §7).

**Wire mapping note (v0 fixture).** The backend fixture
`backend/fixtures/command_v0.json` nests the action as
`action: {cooling: "ON", duty: 1.0}` and uses RFC 3339 timestamp strings plus
audit fields (`controller_id`, `policy_version`, `prediction_id`, `run_id`,
`expected_twin_version`, `reason_code`). `CommandRequest` is the normalized,
typed form used by the pure validator: W04/W-C integration must parse/validate
the wire JSON, map `action.cooling → action`, `action.duty → duty`, and convert
timestamps to epoch seconds. The audit fields are not validation inputs in W03;
they must be persisted/logged by the command layer. W03 does not claim to parse
the fixture.

### 1.2 Local safety evidence

| Field | Meaning |
|---|---|
| `device_mode` | Doc 02 §2.1 device mode; must be an actual `DeviceMode` member |
| `policy_state` | Current policy decision state; must be an actual `PolicyState` member |
| `thermal_quality` | VALID / DEGRADED / INVALID / UNKNOWN; must be an actual `QualityState` member |
| `thermal_age_s` | Age of the physical state used for the check; finite, non-negative |
| `fan_available` | `True` only when heat rejection is confirmed; `None` is not healthy; must be `bool` or `None` |
| `active_fault` | Fault currently asserted; must be an actual `bool` |
| `hardware_safety_condition` | Characterized hardware stop asserted; must be an actual `bool` |

### 1.3 Context

`now_s`, `expected_device_id`, `processed: Mapping[command_id, AckStatus]` and
the versioned `PolicyConfig`. All are explicit; the validator has no clock or
global mutable state of its own. `now_s` must be a finite number; `bool` is
rejected even though `float(True)` is finite (it is not a timestamp).

## 2. Check order (normative, Doc 02 §63)

The first failing check wins.

| # | Check | Reject status | Reason code | Detail |
|---|---|---|---|---|
| 1 | Schema: version, required fields, finite timestamps, expiry > creation, non-retained | `REJECTED` | `INVALID_JSON` | Malformed/unknown command |
| 2 | Authorization assertion | `REJECTED` | `AUTHORIZATION_FAILED` | 05D §28 supplementary vocabulary |
| 3 | Device identity | `REJECTED` | `COMMAND_WRONG_DEVICE` | Doc 02 alias: `DEVICE_ID_MISMATCH` |
| 4 | Clock sanity + expiry | `REJECTED` / `EXPIRED` | `INVALID_JSON` / `COMMAND_EXPIRED` | Future timestamp or TTL elapsed |
| 5 | Duplicate `command_id` | `DUPLICATE_CANONICAL` | `COMMAND_DUPLICATE` | Return canonical status, never re-actuate |
| 6 | Action/duty range | `OUT_OF_RANGE` | `COMMAND_OUT_OF_RANGE` | Non-PWM config rejects duty; PWM uses characterized bounds; OFF with non-zero duty rejected |
| 7 | Local safety | `SAFETY_BLOCKED` | `COMMAND_SAFETY_BLOCKED` | Hardware stop, fault/lockout, fan not confirmed, invalid/unknown thermal state |
| 8 | Mode + state freshness | `INVALID_STATE` | `COMMAND_SAFETY_BLOCKED` / `COMMAND_STATE_STALE` | Mode must accept remote commands; state age must be finite, non-negative and within bound (NaN/±inf rejected, not treated as fresh) |

Evidence vocabulary and safety booleans are checked after the range check and
before check 7. If `device_mode`, `policy_state` or `thermal_quality` is a
look-alike raw value (for example the string `"FAULT_LOCKOUT"`) rather than an
actual enum member, or if `active_fault`/`hardware_safety_condition` is not a
real `bool` (or `fan_available` is neither `bool` nor `None`), the result is
`INVALID_STATE` / `COMMAND_SAFETY_BLOCKED`. A truthy `"false"` is not treated
as an asserted fault, and a falsy `""`/`0` is not treated as a cleared fault.
The documented OFF exception does not apply: it requires a *recognized*
`FAULT_LOCKOUT` or plain fault state with well-typed evidence, not an unknown
one.

Why this order:

- schema before everything: an unparseable command cannot be judged;
- authorization/device before expiry: a command that was never for this device
  is not this device's event;
- expiry before duplicate: a stale duplicate must remain expired, not look
  actionable;
- safety before freshness: the safe direction is known even if state is stale;
- freshness last: it refines permission, it does not override a safety block.

## 3. ACK semantics

| ACK status | Meaning | May actuate? |
|---|---|---|
| `ACCEPTED` | All checks passed at this layer | At most a request; physical actuation still needs W04/W12 |
| `REJECTED` | Schema/authorization/device problem | No |
| `EXPIRED` | TTL elapsed | No |
| `DUPLICATE_CANONICAL` | `command_id` already processed; canonical result returned | No second actuation |
| `OUT_OF_RANGE` | Action/duty outside the characterized family | No |
| `SAFETY_BLOCKED` | Local safety condition forbids action | No |
| `INVALID_STATE` | Mode/freshness does not permit remote control | No |

`ACCEPTED` is not physical proof. An ACK only confirms protocol handling
(Doc 02 §32.2, SW-SAFE-008). Physical verification (applied/current/thermal
response) is a separate state owned by W04/W11/W12.

## 4. Safe-direction rule

- `OFF` is accepted in a recognized `FAULT_LOCKOUT` (and during a plain fault)
  when the mode, timing and state-freshness checks are otherwise valid, the
  evidence enums are actual members and the fault/safety/fan fields are
  well-typed (`bool`, or `bool`/`None` for `fan_available`). OFF is the
  idempotent safe direction; accepting it does not create a new hazard.
  Malformed evidence is rejected for both directions because the state is
  unrecognized.
- `ON` is blocked by an active fault, lockout state, hardware stop, unconfirmed
  fan, or INVALID/UNKNOWN thermal quality.
- A `DEGRADED` but usable thermal state may still allow ON if the rest of the
  safety evidence holds; degraded rules belong to Member A/W11 and are not
  reinterpreted as VALID here.
- An `UNKNOWN`/`None` fan state is blocked, never treated as healthy.

## 5. Duplicate semantics

The caller supplies the processed-command map. On a repeat:

```text
status           = DUPLICATE_CANONICAL
canonical_status = original ACK status
actuation_intent = HOLD
```

The validator never publishes or re-applies the command. The persistence window
is not frozen here; it must cover the maximum plausible replay/reconnect window
and be owned by C/A (W04/W05).

## 6. Reason-code mapping

| Event | W03 code | Doc 02 §58/59 relationship |
|---|---|---|
| Wrong device | `COMMAND_WRONG_DEVICE` | 05D §28; Doc 02 alias `DEVICE_ID_MISMATCH` |
| Unauthorized path | `AUTHORIZATION_FAILED` | 05D §28 |
| Expired | `COMMAND_EXPIRED` | Doc 02 §58; aggregate alias `COMMAND_REJECTED_STALE` |
| Duplicate | `COMMAND_DUPLICATE` | Doc 02 §58; aggregate alias `COMMAND_REJECTED_DUPLICATE` |
| Out of range | `COMMAND_OUT_OF_RANGE` | Doc 02 §58; aggregate alias `COMMAND_REJECTED_RANGE` |
| Safety blocked | `COMMAND_SAFETY_BLOCKED` | Doc 02 §58; aggregate alias `COMMAND_REJECTED_SAFETY` |
| Stale state | `COMMAND_STATE_STALE` | Doc 02 §58 |
| Accepted | `OK` | Doc 02 §64 ACK example sentinel; not a decision reason |

A single event emits one canonical rejection code; aggregate aliases are kept
for audit queries and must not be emitted alongside it for the same event.

## 7. Explicit gaps / not contracted

1. **Authorization verification.** `authorized` is asserted by the caller. The
   pure validator cannot verify JWT/certificate/role/signature. Backend authz
   and broker identity are P0 requirements in
   `evidence/D/W01/security-baseline-v0.md`; W04 must show the assertion cannot
   be forged.
2. **Clock skew bound.** `command_max_future_skew_s` is mandatory but not
   characterized. Exact NTP/clock-drift policy is A/C scope.
3. **Dedup persistence.** W03 unit tests may supply an in-memory map; production reboot/reconnect
   persistence and retention window are not implemented here.
4. **Duty/PWM.** With PWM disabled, only omitted duty or `1.0` is accepted; an
   intermediate duty is rejected. PWM bounds are only used when explicitly
   configured; no physical PWM range is frozen.
5. **Physical verification.** No applied-state/current/thermal-response check is
   part of W03; `ACCEPTED` must not be displayed as "cooling confirmed".
6. **Transport semantics.** QoS 1, non-retained delivery, topic names and broker
   ACLs are requirements owned by W04/C; this function does not implement MQTT.
7. **Terminal ACK after execution.** The W03 contract returns a decision; the device ACK
   lifecycle (accepted → applied → verified) is W04/W12.

## 8. Decision pseudo-code

```text
schema? authorization? device? clock/expiry? duplicate? range?
  -> reject with the first failure
safety?
  -> SAFETY_BLOCKED (ON only; OFF remains the safe direction)
mode/freshness?
  -> INVALID_STATE
else
  -> ACCEPTED (intent ON/OFF), never a physical claim
```
