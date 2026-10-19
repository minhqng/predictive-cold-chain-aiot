# W03 command decision matrix

**Implementation:** `control/src/coldguard_control/commands.py`
**Tests:** `control/tests/test_command_matrix.py` (33 tests) plus the
fail-closed command-freshness case in `control/tests/test_nonfinite.py` (`CM-33`),
the enum/type regressions in `control/tests/test_enum_types.py` (`CM-34`–`CM-36`),
and the boolean regressions in `control/tests/test_bool_types.py`
(`CM-37`–`CM-38`).
**Contract source:** Doc 02 §31–32/§58/§63; Doc 05D §28/D-W03-02.
**Inputs:** synthetic command `cmd-synthetic-001`, device `cg-test-001`,
`now_s = 1010`, created 1000, expires 1030; synthetic `PolicyConfig` and
local-safety evidence. No real device, broker or payload was used.
**Wire cross-check:** the normalized duty rule accepts the v0 fixture's
`action.duty = 1.0` for full-load ON, while an intermediate duty on a non-PWM
configuration is rejected. The validator does not parse the nested JSON or
timestamps; that mapping is W04 scope.

## 1. Required cases

| ID | Case | Input variation | Expected | Observed | Test |
|---|---|---|---|---|---|
| CM-01 | Fresh valid ON | authorized, right device, unexpired, fan confirmed, VALID thermal, fresh state, ONLINE_NORMAL | `ACCEPTED`, intent ON, `OK`, all 8 checks | Same | `test_fresh_valid_on_is_accepted` |
| CM-02 | Expired | `expires_at = now_s` | `EXPIRED`, `COMMAND_EXPIRED`, no actuation | Same | `test_expired_command_is_rejected` |
| CM-03 | Duplicate | processed map contains `cmd-synthetic-001 → SAFETY_BLOCKED` | `DUPLICATE_CANONICAL`, `COMMAND_DUPLICATE`, HOLD, canonical status returned | Same | `test_duplicate_returns_canonical_status_without_reactuating` |
| CM-04 | Wrong device | `device_id = cg-other-999` | `REJECTED`, `COMMAND_WRONG_DEVICE` | Same | `test_wrong_device_is_rejected_before_expiry` |
| CM-05 | Out of range | intermediate duty (e.g. 0.5) on non-PWM config | `OUT_OF_RANGE`, `COMMAND_OUT_OF_RANGE` | Same | `test_duty_on_non_pwm_configuration_is_out_of_range` |
| CM-06 | Invalid state | mode SAFE_LOCAL / stale state | `INVALID_STATE`, `COMMAND_SAFETY_BLOCKED` or `COMMAND_STATE_STALE` | Same | `test_safe_local_mode_rejects_remote_command`, `test_stale_local_state_rejects_command` |
| CM-07 | Safety fault | active fault/lockout/hardware stop/fan unknown/invalid thermal | `SAFETY_BLOCKED`, `COMMAND_SAFETY_BLOCKED` | Same | `test_active_fault_blocks_energization`, `test_unknown_fan_state_is_not_treated_as_healthy`, `test_invalid_thermal_quality_blocks_energization` |

## 2. Additional matrix rows

| ID | Case | Expected | Test |
|---|---|---|---|
| CM-08 | Fresh OFF | `ACCEPTED`, intent OFF | `test_fresh_off_is_accepted` |
| CM-09 | OFF in FAULT_LOCKOUT | `ACCEPTED` (safe direction), intent OFF | `test_off_remains_accepted_during_fault_lockout` |
| CM-10 | ON in FAULT_LOCKOUT / blocking policy state | `SAFETY_BLOCKED` | `test_lockout_policy_state_blocks_energization` |
| CM-11 | Hardware safety stop | `SAFETY_BLOCKED` | `test_hardware_safety_condition_blocks_energization` |
| CM-12 | Fan False | `SAFETY_BLOCKED` | `test_fan_unavailable_blocks_energization` |
| CM-13 | Fan None/UNKNOWN | `SAFETY_BLOCKED`; UNKNOWN is not healthy | `test_unknown_fan_state_is_not_treated_as_healthy` |
| CM-14 | Invalid/UNKNOWN thermal | `SAFETY_BLOCKED` | `test_invalid_thermal_quality_blocks_energization` |
| CM-15 | Missing state age | `INVALID_STATE`, `COMMAND_STATE_STALE` | `test_missing_local_state_age_rejects_command` |
| CM-16 | Boot/self-test mode | `INVALID_STATE` | `test_boot_mode_rejects_remote_command` |
| CM-17 | Unsupported schema | `REJECTED`, `INVALID_JSON` | `test_unsupported_schema_is_rejected` |
| CM-18 | Retained command | `REJECTED`, `INVALID_JSON` | `test_retained_command_is_rejected` |
| CM-19 | `expires_at <= created_at` | `REJECTED`, `INVALID_JSON` | `test_expiry_not_later_than_creation_is_rejected_as_schema` |
| CM-20 | Created implausibly in future | `REJECTED`, `INVALID_JSON` | `test_command_from_far_future_is_rejected` |
| CM-21 | Unauthorized path | `REJECTED`, `AUTHORIZATION_FAILED` | `test_unauthorized_command_is_rejected` |
| CM-22 | Empty command id | `REJECTED`, `INVALID_JSON` | `test_empty_command_id_is_rejected` |
| CM-23 | PWM enabled, duty in range | `ACCEPTED` | `test_pwm_enabled_on_inside_range_is_accepted` |
| CM-24 | PWM enabled, duty missing | `OUT_OF_RANGE` | `test_pwm_enabled_on_without_duty_is_out_of_range` |
| CM-25 | PWM enabled, duty outside range | `OUT_OF_RANGE` | `test_pwm_duty_outside_characterized_range_is_out_of_range` |
| CM-26 | OFF with non-zero duty | `OUT_OF_RANGE` | `test_off_with_nonzero_duty_is_out_of_range` |
| CM-27 | Expired duplicate | `EXPIRED` (expiry before duplicate) | `test_expiry_is_checked_before_duplicate` |
| CM-28 | Safety fault + stale state | `SAFETY_BLOCKED` (safety before freshness) | `test_safety_is_checked_before_state_freshness` |
| CM-29 | Accepted decision wording | Says physical verification remains outside W03 | `test_accepted_decision_does_not_claim_physical_verification` |
| CM-30 | Non-boolean authorization | `REJECTED`, `INVALID_JSON` (no truthy string bypass) | `test_non_boolean_authorization_is_a_schema_error` |
| CM-31 | Boolean schema version | `REJECTED`, `INVALID_JSON` (bool is not integer 1) | `test_boolean_schema_version_is_not_accepted_as_integer_one` |
| CM-32 | Full-load ON duty on non-PWM config (matches v0 fixture `action.duty=1.0`) | `ACCEPTED`, intent ON | `test_full_duty_on_non_pwm_configuration_matches_wire_fixture` |
| CM-33 | Non-finite (`NaN`/`±inf`) or negative `thermal_age_s` | `INVALID_STATE`, `COMMAND_STATE_STALE`, HOLD (fail-closed; NaN must not pass `age > max`) | `test_command_state_freshness_rejects_nonfinite_or_negative_age` |
| CM-34 | Raw string/type for `device_mode`, `policy_state` or `thermal_quality` (e.g. `"FAULT_LOCKOUT"`, `1`) | `INVALID_STATE`, `COMMAND_SAFETY_BLOCKED`, HOLD (not accepted; no gate bypass) | `test_malformed_evidence_is_invalid_state` |
| CM-35 | Malformed evidence + OFF | `INVALID_STATE` (OFF exception requires a recognized state) | `test_malformed_evidence_rejects_off_too` |
| CM-36 | Boolean/non-number `now_s` | `ValueError` before schema evaluation (`float(True)` is finite but invalid) | `test_now_s_rejects_bool_and_non_number` |
| CM-37 | Non-bool `active_fault`, `hardware_safety_condition` or `fan_available` (e.g. truthy `"false"`, falsy `""`/`0`) | `INVALID_STATE`, `COMMAND_SAFETY_BLOCKED`, HOLD for ON and OFF | `test_malformed_evidence_safety_flags`, `test_malformed_evidence_fan_available`, `test_malformed_evidence_bools_reject_off` |
| CM-38 | Well-typed `fan_available` (`True`/`False`/`None`) + OFF | `ACCEPTED`, intent OFF (safe direction preserved; bool typing adds no new state rule) | `test_valid_evidence_fan_available_preserves_off` |

## 3. Check-order evidence

The validator appends each passed check in order. An accepted command returns:

```text
("schema", "authorization", "device_identity", "expiry", "duplicate",
 "range", "safety", "state_freshness")
```

A schema failure returns an empty `checks_passed`; later failures return the
prefix already passed. Two order-sensitive tests confirm that:

- wrong device beats expiry (`CM-04`);
- expiry beats duplicate (`CM-27`);
- safety beats state freshness (`CM-28`).

## 4. Expected vs observed summary

| Required matrix case | Expected | Observed | Verdict |
|---|---|---|---|
| Fresh valid ON | Accepted | Accepted | PASS |
| Expired | Expired/no action | Expired/no action | PASS |
| Duplicate | Canonical status/no re-actuation | Canonical status/HOLD | PASS |
| Wrong device | Rejected | Rejected | PASS |
| Out of range | Out of range | Out of range | PASS |
| Invalid state | Invalid state/no action | Invalid state/no action | PASS |
| Safety fault | Safety blocked/no action | Safety blocked/no action | PASS |

## 5. Limitations

- All values are synthetic. No wire-format encoding, MQTT QoS/retain behavior,
  broker ACL, backend authz or device ACK was exercised.
- `authorized` is an asserted input; the pure validator cannot verify a token,
  certificate or signature.
- Non-finite/negative state ages now fail closed (`CM-33`); the exact freshness
  bound itself is still synthetic and unfrozen.
- Malformed evidence enums fail closed for both ON and OFF (`CM-34`/`CM-35`);
  the documented safe-OFF path is preserved only for recognized members.
- Non-bool safety flags fail closed for both ON and OFF (`CM-37`); a truthy
  `"false"` cannot count as an asserted fault and `""`/`0` cannot clear one.
- Dedup state is supplied by the caller; cross-reboot persistence is not tested.
- PWM bounds are only test values; no physical PWM range is frozen.
- `ACCEPTED` is not physical verification; applied/current/thermal-response
  evidence is W04/W11/W12 scope.
