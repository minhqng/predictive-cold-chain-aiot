# W06 → Members C and D — device command contract

Slice: **A-W06 command/ACK foundation** · Delivered: 2026-11-02 · Branch
`feat/a-w06-command-ack`

What C and D can consume now: the device-side verdict vocabulary, the exact
conditions behind each verdict, and one decision that changes what the backend
will see on the wire. **There is no transport**, so nothing here has been
exchanged with a real broker.

## 1. The decision that affects Member C immediately

**With no synchronized device clock, this device rejects every command whose
absolute expiry it cannot evaluate.** Not silently, and not as `EXPIRED` — as
`SAFETY_BLOCKED` with `reason=EPOCH_UNSYNCHRONIZED` and `expiry_evaluable=0`.

Consequences to design around:

* Until the clock is synchronized, **no remote command can be accepted**,
  including a stop request. That is deliberate: a TTL measured from device receipt
  would prove only that the record arrived recently, not that it was not sitting
  in a queue, and substituting it would quietly weaken `docs/02` §28.1/§31.1.
* Local protections are unaffected and are not routed through this path: the
  console `STOP`/`ESTOP` verbs, the heartbeat timeout, the fault latch and the
  compile-out of the output stage all remain, and they do not require a command
  contract.
* To make remote control usable, one of these has to happen — and it is C's (or
  the project's) call, not a Member A firmware edit:
  1. **time synchronization** on the device (SNTP or a gateway-provided
     synchronized epoch with a stated accuracy), which makes the canonical rule
     directly evaluable; this is the option that changes nothing in the contract;
  2. a **contract amendment** adding a relative-freshness field (e.g.
     `ttl_ms` interpreted from receipt) *plus* an explicit statement of how a
     delayed publish is bounded; this needs `docs/02` §28/§31 changed first, per
     its own authority rules;
  3. accepting that commands remain blocked and documenting predictive actuation
     as not deployable on this device.
* Recommendation: option 1. It preserves the canonical semantics, it is small
  (the device already records `time_sync_state` for exactly this purpose), and it
  does not require anyone to re-read a freshness rule later.

## 2. Device-side contract as implemented

Fields a command must carry. Four of them are the §28.1/§28.2 concepts **renamed for a
flat, unit-explicit device encoding**, not their literal strings: `created_at`→
`created_at_ms`, `expires_at`→`expires_at_ms`, `action.cooling`→`action_cooling`, and
`action.duty` (a 0..1 fraction in docs/02)→`action_duty_permille` (integer per mille).
The rename is deliberate - this device has no float parser on this path and the wire
format must not carry a silent unit conversion - but it is a deviation from the §28.1
spelling and Member C owns the final envelope:

```text
schema_version            must be 1; anything else is UNSUPPORTED_SCHEMA
command_id                canonical 36-char UUID form, or a labelled TEST_TOKEN
device_id                 must equal this device's id
created_at_ms             required; absent => MISSING_CREATED_AT
expires_at_ms             required; absent => MISSING_EXPIRY (never "unbounded")
action_cooling            ON | OFF only
action_duty_permille      0..1000, and inside the device's allowed ceiling
controller_id / policy_version / reason_code   carried, labelled, not interpreted
```

Verdicts — the closed set of §32.1, and nothing else. The parser rejects a name
outside it, and the firmware names an out-of-range status `UNKNOWN` rather than
defaulting it:

| `status` | `reason` examples | meaning |
|---|---|---|
| `ACCEPTED` | `NONE` | every §29 conjunct held. **Not** "cooled". |
| `REJECTED` | `UNSUPPORTED_SCHEMA`, `DEVICE_ID_MISMATCH`, `MISSING_COMMAND_ID`, `MISSING_EXPIRY`, `MISSING_CREATED_AT` | malformed or misaddressed |
| `DUPLICATE_CANONICAL` | the original reason | replay answered from the store, `reapplied=0` |
| `EXPIRED` | `EXPIRED` | clock synchronized and past `expires_at` |
| `SAFETY_BLOCKED` | `EPOCH_UNSYNCHRONIZED`, `OUTPUT_STAGE_COMPILED_OUT`, `LIMITS_UNRESOLVED`, `LOCAL_SAFETY_BLOCKED` | device may not act, whatever the issuer intended |
| `INVALID_STATE` | `SENSORS_INVALID_OR_STALE` | local measurements will not support the action |
| `OUT_OF_RANGE` | `DUTY_ABOVE_ALLOWED_MAX`, `DUTY_NOT_A_PERCENT`, `ON_WITH_ZERO_DUTY`, `OFF_WITH_NONZERO_DUTY`, `BAD_VALIDITY_WINDOW` | action outside the allowed set |

ACK payload (the §32.3 list, plus what makes it interpretable):

```text
schema=1 (command envelope; NOT the serial telemetry schema, which is 3)
command_id  command_id_form  source  device_id  boot_id  boot_count
uptime_ms   ack_seq          status  reason
desired_cooling      desired_duty_permille
applied_cooling      applied_duty_permille      reapplied
expiry_evaluable     time_sync_state            device_mode
output_stage         allowed_duty_max_permille  fault_code
```

Parse a real ACK with `firmware/tools/cg_command_trace.py` (it also demonstrates
the lifecycle stage rules) or against the raw fields in
`evidence/A/W06/ack-fixture.json`.

## 3. Three properties C must not accidentally break

1. **Idempotency memory is volatile, 8 entries.** A restart does not remember
   any `command_id`: `duplicate_recognized=0` after a reset is expected, not a
   bug. C must therefore treat a post-reboot retransmission as a new command and
   must not rely on the device to suppress it — and must not configure the broker
   to retain or redeliver commands across a device restart, which §31.2 forbids
   anyway.
2. **Retention overflow is visible.** `store.evicted` counts ids pushed out of
   the window; if C ever retries a command with more than eight distinct ids in
   between, the device will apply it again. If that is unacceptable for a given
   action, the guarantee has to live in C's layer, not here.
3. **`applied_*` is device truth, `desired_*` is request truth.** Do not derive
   "the device is cooling" from an `ACCEPTED` ACK. The telemetry line carries the
   applied pair on every frame (`cooling_applied`, `pwm_duty`, and from W06
   `desired_cooling` / `last_ack_status`), which is the field set to normalize
   into the twin.

## 4. Mapping to the normalized twin (docs/02 §14.2)

`docs/02` §14.2 already names `applied_cooling`, `applied_duty`,
`*_quality`, `calibration_id`, `hardware_config_id`. The W05+W06 telemetry line
supplies all of them; the mapping C owns:

```text
cooling_applied            -> applied_cooling          (ON/OFF)
pwm_duty                   -> applied_duty             (permille on the wire; normalize per §14.2 units)
desired_cooling            -> desired state, not part of §14.2; store for audit
last_ack_status/reason     -> command lifecycle join (docs/02 §33) via command_id + boot_id + ack_seq
cooling_energy_counter_wh  -> energy_wh                (cumulative; wrap policy is C's)
quality / *_quality          -> overall_quality / per-source quality
```

`command_id` is the join key from the `#CG CMDACK` line to the row in
`#CG TELEM` that carries `command_id=` with the same `boot_id`.

## 5. For Member D

* The device refuses to treat unverifiable freshness as fresh, so **the safety
  hierarchy does not depend on a command being honoured.** If D wants remote stop
  to be available before time sync exists, that is a policy/contract change
  (stop-class commands exempt from absolute expiry, say so in `docs/02`) — and a
  decision D should make explicitly rather than discover in firmware.
* `fault_code`, `output_stage`, `allowed_duty_max_permille` and `time_sync_state`
  on every ACK are the fields D's local policy can reason about without assuming
  anything about the backend.
* `device_mode` is the controller state (`OFF`/`ARMED`/`COOLING`/`COOLDOWN`/
  `FAULT_LATCH`), **not** a §23 policy mode. This firmware runs no policy state
  machine, and naming one would attribute a decision to code that never made it.
* The local `STOP`/`ESTOP` console verbs, the heartbeat timeout and the fault
  latch remain the only stop paths that do not require a command contract.

## 6. Open contract items (not Member A decisions)

1. Time synchronization or an expiry-semantics amendment (§1 above) — blocking for
   remote actuation.
2. The device-side record encoding is `key=value` over the §28.1 names; if C's
   gateway delivers JSON, someone must translate, and the field-name set must
   stay 1:1 with §28.1.
3. Whether `command_id` must be a strict UUID (the parser currently accepts a
   canonical UUID **or** a labelled test token and records which).
4. `docs/02` §33 lifecycle states: the device emits §32.1 verdicts only; mapping
   `ELECTRICAL_VERIFIED`/`THERMAL_VERIFIED` is a backend join across the streams
   (see `cg_command_trace.py` for a rule set that does it honestly).
5. Retention size (8) is a Member A implementation bound; if the retransmission
   window C configures is longer, say so and it will be raised.
