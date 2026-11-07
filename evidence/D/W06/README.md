# W06 evidence — Command negative tests and lifecycle integration

**Date:** 2026-11-07
**Owner:** Member D (control / safety / security / resilience)
**Parent issues:** 05D D-W06-01 through D-W06-06

## Goal

Prove transport retry/stale inputs do not produce unsafe physical behavior (05D section 38):
* Expired command → REJECTED, no actuation;
* Duplicate command → one logical application, canonical ACK;
* Wrong-device → reject;
* Out-of-range → reject;
* Invalid-state command → SAFETY_BLOCKED / INVALID_STATE;
* ACK interpretation → never equates accepted ACK with verified cooling.

## Deliverables

| Deliverable | Location | State |
|---|---|---|
| Command TTL validation | `control/src/coldguard_control/commands.py` | Implemented |
| Clock sync gate | `control/src/coldguard_control/commands.py` | Implemented |
| TTL unit tests | `control/tests/test_command_ttl.py` | 11 tests |
| Command matrix tests | `control/tests/test_command_matrix.py` | 33 tests |
| PhysicalVerificationState | `control/src/coldguard_control/types.py` | Added |

## Test results

From `control/`:

```powershell
uv run --locked --extra test pytest tests/test_command_ttl.py tests/test_command_matrix.py -v
```

```text
44 passed
```

## Key test scenarios

### D-W06-01 Expired command

```python
test_expired_command_is_rejected()
```
Expected: `EXPIRED`, `COMMAND_EXPIRED`, `may_actuate=False`

### D-W06-02 Duplicate command

```python
test_duplicate_returns_canonical_status_without_reactuating()
test_duplicate_returns_original_rejection_reason()
```
Expected: `DUPLICATE_CANONICAL`, original status preserved, `HOLD` intent

### D-W06-03 Wrong-device

```python
test_wrong_device_is_rejected_before_expiry()
```
Expected: `REJECTED`, `COMMAND_WRONG_DEVICE`

### D-W06-04 Out-of-range

```python
test_duty_on_non_pwm_configuration_is_out_of_range()
test_pwm_duty_outside_characterized_range_is_out_of_range()
```
Expected: `OUT_OF_RANGE`, `COMMAND_OUT_OF_RANGE`

### D-W06-05 Invalid-state command

```python
test_safe_local_mode_rejects_remote_command()
test_stale_local_state_rejects_command()
test_active_fault_blocks_energization()
```
Expected: `INVALID_STATE` or `SAFETY_BLOCKED`, `COMMAND_SAFETY_BLOCKED` or `COMMAND_STATE_STALE`

### D-W06-06 ACK interpretation

```python
test_accepted_decision_does_not_claim_physical_verification()
```
Expected: `detail` includes "physical verification ... outside W03"

## Check order (Doc 02 section 63)

The command validator checks in this order:

1. Schema
2. Authorization
3. Device identity
4. Expiry (absolute + TTL bounds)
5. Duplicate
6. Range
7. Safety
8. State freshness

First failing check wins so the returned reason is stable and auditable.

## TTL semantics (05D section 9, Doc 02 section 31)

| Situation | Verdict | Why |
|---|---|---|
| `now > expires_at` | `EXPIRED` | Absolute expiry is authoritative |
| `now - created_at > command_max_age_s` | `EXPIRED` | Age since issue exceeds bound |
| `expires_at - created_at > command_max_ttl_s` | `OUT_OF_RANGE` | Validity window too long |
| Clock unsynchronized | `SAFETY_BLOCKED` | Cannot evaluate expiry |

## Acceptance status

| Requirement | Status | Evidence |
|---|---|---|
| D-W06-01 Expired command | PASS | `test_expired_command_is_rejected()` |
| D-W06-02 Duplicate command | PASS | `test_duplicate_*()` tests |
| D-W06-03 Wrong-device | PASS | `test_wrong_device_is_rejected_before_expiry()` |
| D-W06-04 Out-of-range | PASS | `test_duty_*_is_out_of_range()` tests |
| D-W06-05 Invalid-state | PASS | `test_*_blocks_*()` tests |
| D-W06-06 ACK interpretation | PASS | `test_accepted_decision_does_not_claim_physical_verification()` |

## Open items

| Item | Owner | Next action |
|---|---|---|
| Backend ACK persistence | C | Store command ACK in database with lifecycle status |
| MQTT topic configuration | C | Configure `command` topic with QoS 1, retain=false |
| Cross-reset idempotency | A/firmware | Decide whether to persist command IDs across reboot |
| Physical command trace | A/C | End-to-end test: backend → MQTT → device → ACK → backend |

## Read order

1. `commands.py` — `validate_command()` and `_validate_ttl()`
2. `test_command_ttl.py` — TTL test scenarios
3. `test_command_matrix.py` — command decision matrix (33 tests)
4. Doc 02 section 31 — command freshness contract
5. 05D section 38 — W06 objectives
