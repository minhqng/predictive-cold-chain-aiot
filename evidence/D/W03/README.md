# W03 evidence — pure policy unit, command matrix, failure taxonomy

## Goal

Make control decisions deterministic and testable independently of hardware:
a pure `PolicyInput → PolicyDecision` function, a command decision matrix, a
Doc 01 failure taxonomy, and unit assertions that local protection dominates
prediction and faults dominate optimization.

This is **Member D W03**, not Member C's backend W03. No backend, broker,
database or firmware feature is claimed complete here.

## Deliverables

| Deliverable | Location | State |
|---|---|---|
| Pure policy + config + vocabulary | `control/src/coldguard_control/{policy,config,types}.py` | Implemented |
| Command validator | `control/src/coldguard_control/commands.py` | Implemented |
| Failure taxonomy | `control/src/coldguard_control/taxonomy.py` | Implemented |
| Public exports | `control/src/coldguard_control/__init__.py` | Exported |
| Unit tests | `control/tests/test_*.py` | 319 passed |
| Command matrix evidence | `command-matrix.md` | Complete |
| Taxonomy evidence | `failure-taxonomy.md` | Complete |
| Policy unit notes | `policy-unit.md` | Complete |

## Environment / versions

```text
date:        2026-10-19
OS:          Windows 11 Home (10.0.26200), win32
Python:      3.12.10
uv:          0.13.1 (62faed335 2026-10-13)
pytest:      9.1.1
package:     coldguard-control 0.1.0
policy:      "test-policy-synthetic-v0" (synthetic only; no production freeze)
hardware:    none — no sensor, actuator, PSU, broker or device
model:       none — synthetic PredictionView objects only
```

Test command (required form), run from `control/`:

```powershell
uv run --locked --extra test pytest
```

Observed final run:

```text
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: D:\predictive-cold-chain-aiot-main-upstream\control
configfile: pyproject.toml
testpaths: tests
collected 319 items
319 passed in 0.74s
```

`--locked` succeeded; no dependency or lockfile change was required.

## Test inventory

| File | Tests | Purpose |
|---|---|---|
| `tests/test_policy_priorities.py` | 14 | Critical/fault dominance, predictive guard, persistence |
| `tests/test_policy_states.py` | 35 | Hysteresis, 7 states, SAFE_LOCAL entry/exit, input contract |
| `tests/test_command_matrix.py` | 33 | Required 7 command cases + ordering/schema/safety edges |
| `tests/test_nonfinite.py` | 88 | Fail-closed regression for NaN/±inf/bool numerics |
| `tests/test_enum_types.py` | 43 | Raw-string/type bypass regression for enum fields |
| `tests/test_bool_types.py` | 66 | Truthiness/boolean bypass regression for trust and safety flags |
| `tests/test_taxonomy.py` | 34 | All 14 failure IDs, dispositions, auditability |
| `tests/test_purity.py` | 5 | No transport/DB/GPIO/web/clock imports, no numeric defaults |
| `tests/test_package.py` | 1 | Import smoke test retained |
| **Total** | **319** | |

Selected IDs:

```text
tests/test_policy_priorities.py::test_critical_protection_beats_fresh_predictive_warning
tests/test_policy_priorities.py::test_plain_fault_beats_every_predictive_optimization
tests/test_policy_priorities.py::test_stale_prediction_is_never_reused_for_actuation
tests/test_policy_states.py::test_reconnect_alone_does_not_restore_remote_trust
tests/test_policy_states.py::test_safe_local_exits_only_when_every_requirement_holds
tests/test_command_matrix.py::test_fresh_valid_on_is_accepted
tests/test_command_matrix.py::test_expired_command_is_rejected
tests/test_command_matrix.py::test_duplicate_returns_canonical_status_without_reactuating
tests/test_command_matrix.py::test_wrong_device_is_rejected_before_expiry
tests/test_command_matrix.py::test_duty_on_non_pwm_configuration_is_out_of_range
tests/test_command_matrix.py::test_safe_local_mode_rejects_remote_command
tests/test_command_matrix.py::test_active_fault_blocks_energization
tests/test_taxonomy.py::test_uncontracted_rules_are_explicit
tests/test_purity.py::test_core_imports_no_transport_db_gpio_or_web_modules
tests/test_nonfinite.py::test_required_config_number_must_be_finite
tests/test_nonfinite.py::test_remote_timing_must_be_finite
tests/test_nonfinite.py::test_safe_local_exit_never_satisfied_by_nonfinite_network_stable
tests/test_nonfinite.py::test_command_state_freshness_rejects_nonfinite_or_negative_age
tests/test_enum_types.py::test_raw_string_fault_lockout_with_high_temperature_is_rejected
tests/test_enum_types.py::test_malformed_evidence_is_invalid_state
tests/test_enum_types.py::test_recognized_fault_lockout_still_accepts_safe_off
tests/test_bool_types.py::test_remote_flags_must_be_actual_bool
tests/test_bool_types.py::test_safe_local_exit_fails_closed_on_malformed_trust_flags
tests/test_bool_types.py::test_valid_evidence_fan_available_preserves_off
```

## Expected vs observed

| Requirement | Expected | Observed | Verdict |
|---|---|---|---|
| Pure `PolicyInput → PolicyDecision` | No MQTT/DB/GPIO/FastAPI/hardware in core | AST import/call guards pass; no clock or global state | PASS |
| Seven-state policy | All states reachable per gate/transition table | Enum + tests | PASS |
| CRITICAL > PREEMPTIVE | Critical wins with a fresh 0.99 score | `CRITICAL_PROTECTION`, Controller A, ON | PASS |
| FAULT > optimization | Fault wins with a fresh 0.99 score | `FAULT`, HOLD, predictive blocked | PASS |
| Command matrix (7 cases) | Fresh ON, expired, duplicate, wrong device, range, invalid state, safety fault | All covered; see `command-matrix.md` | PASS |
| Failure taxonomy | Map all 14 Doc 01 §28 failures; no silent ignore | 14 rows; 4 `NOT_CONTRACTED`; no `IGNORE` member | PASS |
| Negative tests | Invalid/stale/substituted values rejected | `PolicyInputError`/`ConfigError` tests pass | PASS |
| Non-finite inputs fail closed | NaN/±inf never treated as fresh/stable/in-range | Rejected at config, policy input, SAFE_LOCAL exit and command freshness (`test_nonfinite.py`, 88 tests) | PASS |
| Enum fields are runtime-checked | Raw strings/types cannot bypass state or mode gates | `PolicyInput`/nested and `LocalSafetyEvidence` enums rejected with `PolicyInputError`/`INVALID_STATE`; bool `now_s` rejected (`test_enum_types.py`, 43 tests) | PASS |
| Boolean flags are runtime-checked | Truthy `"false"` cannot look trusted; falsy `""`/`0` cannot clear faults | Policy flags require `bool`, `fan_available` `bool`/`None`; direct exit reports malformed flags missing; evidence bools reject both ON/OFF (`test_bool_types.py`, 66 tests) | PASS |
| Synthetic-only thresholds | No physical number in package defaults | `PolicyConfig` numeric fields have no defaults | PASS |
| Scope discipline | No real controller, MQTT publish, DB, GPIO or actuation | No such imports/calls/output fields | PASS |

## What was deliberately not done

- No real Controller A/B, control loop, scheduler, watchdog or runtime state
  store.
- No MQTT publish/subscribe, broker, database, FastAPI, GPIO or hardware access.
- No predictive actuator output; `actuation_intent` is a decision label only.
- No physical fault injection, no device command, no sensor reading.
- No invented thermal threshold, TTL, dwell, duty range or safe-local timing.
- No claim that a command ACK equals physical cooling.
- No edits to Member A/B/C code or ownership.
- No repair of Member C's W03 backend scope, and no implication that its
  completion would complete Member D W03.

## Verdict

**W03 unit-level scope: PASS**, with the limitations below. This proves branch
logic and priority invariants only. It does not prove plant safety, transport
security, timing deadlines or physical actuation.

## Limitations / unverified

1. All numbers are synthetic test values; real values await A's
   characterization and B's frozen warning contract.
2. Stale-state handling (`FAULT` + HOLD) is provisional pending W05.
3. Generic `FAULT` incident action and lockout/reset are not contracted; W10
   and W11 own them.
4. `authorized` is an asserted input; backend authz, broker identity/ACL and TLS
   are unverified P0 items (see W01).
5. Duplicate-state persistence across reboot/reconnect is caller-supplied; no
   cross-restart test exists.
6. No timing/latency/starvation test; control-task deadlines remain an
   A/firmware hazard (H-11).
7. PWM support is logic-only and disabled by default; no physical duty range is
   frozen.
8. No integration with the actual backend `command_v0.json` wire encoding or
   MQTT topics; only the full-load duty value was cross-checked against the
   fixture. JSON parsing, timestamp conversion and audit-field mapping are W04
   scope.
9. Command expiry checks `now < expires_at` and future creation skew, but the
   pure validator has no configured maximum command age or TTL span. W04 must
   freeze and enforce the Doc 02 TTL bound before transport integration.
10. `evaluate_policy()` validates the type of `fan_available` but does not use
    it to suppress an ON policy intent. `validate_command()` blocks ON unless
    the fan is confirmed; W04/device integration must route every energizing
    decision through that validator and retain the hardware interlock.
11. READY prediction versions are required to be non-empty, but are not checked
    against an expected model/feature version. Keep predictive control disabled
    until Member B publishes the version contract and integration enforces it.
