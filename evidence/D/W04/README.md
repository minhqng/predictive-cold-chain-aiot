# W04 evidence — Command TTL semantics and device safety review

**Date:** 2026-11-07
**Owner:** Member D (control / safety / security / resilience)
**Parent issues:** 05D D-W04-01 through D-W04-05

## Goal

Freeze legal remote actuation semantics around A's first physical TEC tests:
* Define candidate command-validity policy (TTL semantics);
* Device-side safety checklist (boot/reset OFF, H-bridge direction, enable, fan);
* Command/ACK reason codes v0;
* Physical first-actuation review (A's H6 evidence).

## Deliverables

| Deliverable | Location | State |
|---|---|---|
| TTL semantics (config) | `control/src/coldguard_control/config.py` | Implemented |
| Device safety contract | `control/src/coldguard_control/device_safety.py` | Implemented |
| Command TTL validation | `control/src/coldguard_control/commands.py` | Implemented |
| TTL unit tests | `control/tests/test_command_ttl.py` | 11 tests |
| Device safety tests | `control/tests/test_device_safety.py` | 18 tests |
| PhysicalVerificationState enum | `control/src/coldguard_control/types.py` | Added |

## Test results

From `control/`:

```powershell
uv run --locked --extra test pytest
```

```text
370 passed in 0.77s
```

New tests added:
* `test_command_ttl.py` — 11 tests for TTL semantics
* `test_device_safety.py` — 18 tests for device safety checklist

## Key design decisions

### TTL bounds (05D section 9, Doc 02 section 67)

Two optional bounds are now available in `PolicyConfig`:

* `command_max_age_s` — caps `now - created_at` (age since issue time, never since receipt)
* `command_max_ttl_s` — caps `expires_at - created_at` (declared validity window)

Both are `None` by default (not characterized). When supplied, they are enforced **in addition to** the absolute `expires_at` rule.

### Clock synchronization gate (A-W06 handoff)

When `clock_synchronized=False`, command expiry cannot be evaluated. This is a `SAFETY_BLOCKED` condition, not an expiry verdict. The device cannot prove the command is fresh, so it must not actuate. Local protections (Controller A, SAFE_LOCAL) remain available.

### Device safety checklist (05D D-W04-02)

The `check_actuator_safety()` function validates:
* Boot complete, reset not asserted
* At most one H-bridge direction active
* Enable asserted before ON request
* Fan confirmed available (UNKNOWN is not healthy)
* Duty within characterized range
* Unexpected drive while OFF is an electrical anomaly

### Physical verification states (05D section 13)

New enum `PhysicalVerificationState` added to track independent electrical/thermal verification. An ACK only proves protocol handling; it never proves current flowed or the chamber cooled (Doc 02 section 32.2).

## What was deliberately not done

* No frozen numeric TTL values (awaiting A/C characterization)
* No broker/MQTT integration (Member C scope)
* No physical fault injection
* No Secure Boot / Flash Encryption (optional hardening, 05D section 26)
* No claim that ACK equals physical cooling

## Acceptance status

| Requirement | Status | Evidence |
|---|---|---|
| D-W04-01 Legal actions | PASS | `device_safety.py`, `test_device_safety.py` |
| D-W04-02 Device safety checklist | PASS | `check_actuator_safety()`, 18 tests |
| D-W04-03 TTL semantics | PASS | `config.py`, `commands.py`, `test_command_ttl.py` |
| D-W04-04 Reason codes v0 | PASS | `types.py` ReasonCode enum |
| D-W04-05 Physical first-actuation review | PARTIAL | Main now contains A-W04-06 polarity `PASS` and A-W12-03 post-freeze inspection `PASS`; enabled-stage boot/reset/interlock proof, fuse/conductor disposition and G1 approval remain open |

## Open items

| Item | Owner | Next action |
|---|---|---|
| Characterize command_max_age_s | A/C | Measure latency distribution from command issue to physical effect |
| Characterize command_max_ttl_s | A/C | Define maximum acceptable validity window based on use case |
| Clock synchronization implementation | A/firmware | Implement SNTP or gateway-provided synchronized epoch |
| Physical verification integration | C/D | Join command ACK with electrical/thermal evidence in backend |
| Fuse/conductor ampacity disposition | A/hardware owner | Resolve and sign the open deviation retained in A-W12-03 notes |
| G1 decision | Designated gate owner | Review enabled-stage safety package; D does not self-declare the team gate |

## Read order

1. `device_safety.py` — device/actuator safety input contract
2. `config.py` — TTL configuration fields
3. `commands.py` — `_validate_ttl()` and clock sync gate
4. `test_command_ttl.py` — TTL test scenarios
5. `test_device_safety.py` — safety checklist tests
