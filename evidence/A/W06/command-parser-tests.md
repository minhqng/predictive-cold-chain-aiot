# A-W06-01/02/03/04 — Command parser and lifecycle test record

Executed: 2026-11-02 · Method: **host execution of the delivered C sources**
Harness: `firmware/tools/tests/cg_w06_harness.c` (36 scenarios; compiles
`cg_command.c`, `cg_quality.c`, `cg_health.c`, `cg_snapshot.c`, `cg_telemetry.c`,
`cg_tec_control.c`, `cg_tec_limits.c`, `cg_tec_command.c` unchanged) · Checker:
`cg_check_firmware_w06.py` (93 static checks) · Negative tests:
`tests/test_cg_check_firmware_w06.py` (22 tests: 20 in-memory mutations, 1 must-not-fire
control, 1 real-tree baseline) · W06 harness worst-case line measurements in
`build/`

> **Host scenarios, not a bench round trip.** Commands here are synthetic
> records submitted to the delivered validator with an explicit context. There is
> no transport in this firmware, no backend issuer, and no energization, so
> nothing in this file demonstrates a real command reaching a real device. The
> physical deliverables that would require that are named in
> `physical-command-trace.md` and left open.

## 1. The freshness decision (the reason this record exists)

`docs/02` §28.1 gives a command an absolute `created_at` and `expires_at`. This
device has no wall clock and no network time — the same fact that makes its
telemetry print `timestamp_utc=UNAVAILABLE`, and which `docs/01` 2253-2259
answers by requiring uptime, sequence and **synchronization state** to be
recorded rather than a false precision manufactured.

So:

| Situation | Verdict | Why this one |
|---|---|---|
| Clock unsynchronized, expiry in the (issuer's) future | `SAFETY_BLOCKED` / `EPOCH_UNSYNCHRONIZED`, `expiry_evaluable=0` | The device cannot disprove expiry, and it equally cannot prove it. Treating "not disproved" as fresh would actuate on an assumption. |
| Clock unsynchronized, expiry in the past | same | Reporting `EXPIRED` would claim an age the device did not measure. |
| Clock synchronized, `now > expires_at` | `EXPIRED` | Here the comparison is real, so the contract's own word is used. |
| `expires_at` absent | `REJECTED` / `MISSING_EXPIRY` | §28.2 makes expiry required. Reading absence as "never expires" would convert a malformed command into the most dangerous kind: an unbounded one. |
| `created_at` absent | `REJECTED` / `MISSING_CREATED_AT` | Without an issue time the age is unknowable, which is the same failure as an unverifiable expiry but with a distinct, attributable reason. |
| `expires_at <= created_at` | `OUT_OF_RANGE` / `BAD_VALIDITY_WINDOW` | A zero- or negative-length window is a range error, not a freshness result. |

**No receive-time TTL is substituted anywhere.** A TTL measured from device
receipt proves only that the device saw the record recently; it says nothing
about how long the command waited upstream, so it cannot stand in for the
canonical semantics. The checker enforces that structurally: the command layer
contains no `ttl_ms`/`TTL_MS`, no `received_ms +` or `uptime_ms + command->`
arithmetic, and the ARM authorization window (`CG_TEC_ARM_TTL_MS`, a different
pre-existing thing) is asserted not to leak into command expiry.

## 2. Scenario matrix (all 36 pass)

| Group | Scenarios |
|---|---|
| §29 chain, conjunct by conjunct | `unsupported_schema_rejected`, `wrong_device_rejected`, `missing_command_id_rejected` (+ asserts an id-less record occupies no retention slot) |
| Freshness | `missing_expiry_is_not_treated_as_unbounded`, `missing_created_at_rejected`, `inverted_validity_window_rejected`, `unsync_clock_blocks_instead_of_assuming_fresh`, `unsync_clock_blocks_even_a_past_expiry`, `expired_when_synchronized`, `fresh_when_synchronized_reaches_later_checks` |
| Range, safety, state | `duty_above_allowed_max_out_of_range`, `duty_not_a_permille_value`, `on_with_zero_duty_and_off_with_duty_rejected`, `shipped_board_blocks_on_request_even_when_fresh`, `invalid_local_state_rejected` |
| A-W06-04 applied state | `applied_state_comes_from_the_device` — a board that *is* cooling, asked to stop, must ACK with `applied_cooling=ON` while `desired_cooling=OFF`; the applied pair is read from the context, never derived from the request |
| A-W06-02 idempotency | `duplicate_returns_canonical_and_does_not_reapply` (the world is then moved on — ceiling lowered, stage removed — and the replay still answers the **original** verdict), `blocked_duplicate_stays_blocked_canonical`, `new_id_same_action_is_a_new_instruction`, `retention_bound_is_explicit` |
| A-W06-06 reset | `store_is_volatile_across_reset` |
| ACK | `ack_line_carries_the_required_payload`, `ack_duplicate_names_canonical_status`, `ack_refuses_truncation_and_anonymous_records`, `ack_status_vocabulary_is_closed` |
| Encoding + console bridge | `fields_record_parses_canonical_set`, `fields_record_refers_unknown_and_malformed`, `local_test_bridge_is_labelled_and_unbounded_by_choice`, `local_console_command_is_blocked_by_the_validator`, `console_cmdtest_grammar`, `existing_console_verbs_unchanged` |
| Telemetry | `no_command_is_named_not_zeroed`, `desired_and_applied_are_both_published`, `worst_case_fits_after_w06_fields`, `oversized_numbers_are_refused`,
`worst_case_ack_fits_its_budget` |

## 3. Retention and reset semantics, stated exactly

* The store holds `CG_CMD_STORE_CAPACITY = 8` ids in RAM. Eight distinct
  commands fit with **nothing forgotten**: replaying any of them answers
  `DUPLICATE_CANONICAL`. A ninth **distinct** id displaces the oldest, and from
  then on that oldest id is treated as new — `store.evicted` counts each such
  displacement so the bound is observable rather than assumed.
* The store is never written to NVS, and neither is anything else in
  `cg_commission.c`. After a reset the device cannot claim `DUPLICATE_CANONICAL`
  and **must not** resume the earlier desire: `reset-command-log.jsonl` shows the
  same `command_id` accepted before the reset and, after it, re-validated against
  a fresh boot's unresolved limits and reported `OUT_OF_RANGE` with
  `applied_cooling=OFF`, `duplicate_recognized=0`.
* The consequence is named rather than hidden: **cross-reset idempotency is not
  provided.** A retransmission that survives a reboot is re-judged from the safe
  default state, which is the behaviour `docs/02` §31.2-§31.3 asks for; a store
  that persisted identity would be the mechanism by which a stale actuation could
  come back.

## 4. Local console bridge vs the canonical contract

`CMDTEST <id> <ON|OFF> <duty-permille>` submits a record through the **same**
validator, stamped `source=LOCAL_CONSOLE` and `command_id_form=TEST_TOKEN`, with
no `created_at`/`expires_at` — because the device has no clock to stamp them
with and an operator-typed instant is not a synchronized time base. It therefore
cannot obtain an acceptance, and the ACK says which required field is missing.

The separation is deliberate and is checked: the bridge is not the network
contract, it cannot be mistaken for one in the log, and `ACCEPTED` for a local
test id is unreachable in the shipped configuration.

## 5. Defect found in delivered W04 code by this slice

`split_line()` in `cg_tec_command.c` assigned `*verb` only on the **no-argument**
path. Every two-token verb (`ARM`, `CLEAR`, `START`, `RUN`, `PHASE`) therefore
dispatched on an uninitialized pointer — undefined behaviour, latent because no
test had ever parsed those verbs on the host. The first command reaching the
controller could have been mis-dispatched.

Fixed by assigning the verb on both paths; `existing_console_verbs_unchanged` and
a static assertion in `cg_check_firmware_w06.py` (`split_line assigns the verb on
BOTH paths`) now pin it, and a mutation that removes the second assignment fails
the gate. This is disclosed rather than quietly repaired: the W04 acceptance
record keeps its text, and the correction is dated here.

## 6. Explicitly not established here

* No command was ever received by a real device: there is no transport, and the
  W06 build has not been flashed.
* No actuation, no electrical verification, no thermal verification. The output
  stage is compiled out, `CG_TEC_REQUEST_DUTY_PERMILLE` is 0, all six limits
  remain `UNRESOLVED`, and every fixture ACK reports `applied_cooling=OFF` —
  the artifact generator refuses to write a fixture in which it is not.
* No backend ACK path, and no claim about one: `docs/02` §32.3's envelope, the
  MQTT `command_ack` topic and the dedup/retention behaviour at the broker belong
  to Member C. What is delivered here is the device-side rules, field names and
  verdict vocabulary.
* The device-side **encoding** (`key=value` records using the §28.1 field names)
  is Member A's representation pending C's schema decision — the JSON envelope in
  `docs/02` stays C's. The validation rules themselves are transport-independent,
  which is why they were provable before any transport exists.
* `device_mode` in the ACK carries the controller state (e.g. `OFF`), **not** a
  §23 policy mode: policy states belong to Member D's layer and this firmware
  runs none. Naming one would attribute a decision to code that never made it.
