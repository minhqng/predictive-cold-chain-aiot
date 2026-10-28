# W03 policy unit skeleton

**API:** `PolicyInput → PolicyDecision` (pure function).
**Implementation:** `control/src/coldguard_control/policy.py`,
`config.py`, `types.py`.
**Tests:** `test_policy_priorities.py`, `test_policy_states.py`,
`test_purity.py`.

## 1. API shape

```python
decision = evaluate_policy(
    PolicyInput(
        device_mode=...,
        thermal=ThermalView(quality=..., t_representative_c=..., age_s=...),
        applied_cooling=CoolingState.ON | OFF,
        remote=RemotePathView(...),
        prediction=PredictionView(...) | None,
        current_state=PolicyState | None,
        fault_active=...,
        fault_reason=ReasonCode | None,
        control_electrical_anomaly=...,
        hardware_safety_condition=...,
    ),
    PolicyConfig(...),   # no numeric defaults
)
```

The function has no I/O, no clock, no MQTT/DB/GPIO/FastAPI/hardware import, no
global mutable state and no actuator output. It returns one immutable
`PolicyDecision`.

## 2. Priority proofs

`CRITICAL_PROTECTION > PREEMPTIVE`:

```text
T = upper boundary, fresh prediction risk 0.99, persistence 600 s
-> CRITICAL_PROTECTION, ON, Controller A, THRESHOLD_HIGH
```

Test: `test_critical_protection_beats_fresh_predictive_warning`.

`FAULT > optimization`:

```text
active fault + fresh prediction risk 0.99, persistence 600 s
-> FAULT, HOLD, Controller A, predictive_blocked=True
```

Tests: `test_plain_fault_beats_every_predictive_optimization`,
`test_lockout_class_fault_reason_escalates_from_fault_to_lockout`.

Other dominance checks:

- electrical anomaly + hot chamber + high risk → `FAULT_LOCKOUT`
  (`test_control_electrical_anomaly_beats_heat_and_prediction`);
- hardware stop + hot chamber + high risk → `FAULT_LOCKOUT`
  (`test_hardware_safety_condition_beats_heat_and_prediction`);
- invalid thermal state + high risk → `FAULT_LOCKOUT`
  (`test_thermal_fault_blocks_optimization_even_when_prediction_is_fresh`);
- stale prediction → `SAFE_LOCAL`, never a reused score
  (`test_stale_prediction_is_never_reused_for_actuation`).

## 3. Determinism and purity

- Same `(PolicyInput, PolicyConfig)` → equal `PolicyDecision`
  (`test_evaluation_is_deterministic`).
- Core modules import only `__future__`, `dataclasses`, `enum`, `math`, `typing`
  and package-relative modules; transports, DB, GPIO, web, serial, socket and
  clock modules are rejected by an AST test
  (`test_core_imports_no_transport_db_gpio_or_web_modules`).
- Calls to `publish`, `subscribe`, `actuate`, `digital_write`, `gpio_write`,
  `sleep`, `monotonic` are rejected (`test_core_never_calls_...`).
- `PolicyConfig` has no numeric defaults; the required operating values have no
  dataclass defaults (`test_policy_config_has_no_numeric_defaults`,
  `test_required_policy_values_cannot_be_omitted`).
- `PolicyDecision` has no GPIO/MQTT/DB/relay field
  (`test_decision_has_no_actuator_or_transport_fields`).
- Every numeric `PolicyConfig`/`PolicyInput` value is finite; `NaN`/`±inf` and
  `bool` are rejected before any comparison so a broken value cannot fail open
  (`tests/test_nonfinite.py`).
- Every enum-typed `PolicyInput` field and `LocalSafetyEvidence` state field must
  be an actual enum member; raw look-alike strings are rejected before identity
  comparisons (`tests/test_enum_types.py`).
- Every boolean trust/fault/safety field must be an actual `bool`
  (`fan_available`: `bool` or `None`). Non-empty strings such as `"false"` are
  truthy and must not count as trusted/faulted, while `""`/`0` must not clear a
  fault (`tests/test_bool_types.py`).

## 4. Negative / adversarial cases

| Case | Expected | Test |
|---|---|---|
| `VALID` quality without value/age | `PolicyInputError` | `test_valid_quality_requires_value_and_age` |
| `INVALID` quality carrying a substituted value | `PolicyInputError` | `test_invalid_quality_must_not_carry_a_substituted_value` |
| Risk outside [0,1] | `PolicyInputError` | `test_risk_score_outside_unit_interval_is_rejected` |
| Negative age | `PolicyInputError` | `test_negative_age_is_rejected` |
| Unknown door state | `PolicyInputError` | `test_unknown_door_state_is_rejected` |
| BOOT/SELF_TEST | `PolicyPreconditionError` | `test_policy_undefined_before_online_modes` |
| Missing required config | `ConfigError` | Builder/unit config checks |
| Prediction missing while predictive enabled | `SAFE_LOCAL` / `AI_UNAVAILABLE` | `test_unavailable_model_blocks_preemptive_action` |
| Low risk but high persistence | no preemptive action | `test_persistence_gate_separates_watch_from_preemptive` |
| `NaN`/`±inf`/`bool` config numeric | `ConfigError` | `test_required_config_number_must_be_finite`, `test_required_config_number_rejects_bool`, `test_optional_config_number_must_be_finite`, `test_duty_bounds_must_be_finite` |
| `NaN`/`±inf` thermal, prediction or remote timing | `PolicyInputError` | `test_thermal_age_must_be_finite`, `test_prediction_age_must_be_finite`, `test_remote_timing_must_be_finite` |
| `NaN`/`±inf`/negative SAFE_LOCAL exit timing | exit not satisfied | `test_safe_local_exit_never_satisfied_by_nonfinite_network_stable`, `..._backend_age` |
| `NaN`/`±inf`/negative command state age | `INVALID_STATE` / `COMMAND_STATE_STALE` | `test_command_state_freshness_rejects_nonfinite_or_negative_age` |
| Raw `"FAULT_LOCKOUT"` + high temperature | `PolicyInputError` (cannot reach ON) | `test_raw_string_fault_lockout_with_high_temperature_is_rejected` |
| Raw string/type for any `PolicyInput` enum field | `PolicyInputError` | `test_device_mode_must_be_enum_member`, `test_thermal_quality_must_be_enum_member`, `test_applied_cooling_must_be_enum_member`, `test_current_state_must_be_enum_member_when_present`, `test_electrical_quality_must_be_enum_member`, `test_fault_reason_must_be_reason_code_member`, `test_prediction_health_must_be_enum_member` |
| Malformed `LocalSafetyEvidence` enums | `INVALID_STATE` / `COMMAND_SAFETY_BLOCKED` (ON and OFF) | `test_malformed_evidence_is_invalid_state`, `test_malformed_evidence_rejects_off_too` |
| Boolean/non-number `now_s` | `ValueError` | `test_now_s_rejects_bool_and_non_number` |
| Truthy `"false"` / non-bool remote trust flag | `PolicyInputError` | `test_remote_flags_must_be_actual_bool` |
| Truthy `"false"` / falsy `""`/`0` policy fault or safety flag | `PolicyInputError` | `test_policy_safety_flags_must_be_actual_bool` |
| Non-bool `fan_available` | `PolicyInputError` | `test_fan_available_rejects_non_bool` |
| Malformed boolean in direct SAFE_LOCAL exit | exit not satisfied; relevant requirement missing | `test_safe_local_exit_fails_closed_on_malformed_trust_flags`, `..._stale_flag`, `..._fault_flags` |
| Malformed `LocalSafetyEvidence` booleans | `INVALID_STATE` / `COMMAND_SAFETY_BLOCKED` (ON and OFF) | `test_malformed_evidence_safety_flags`, `test_malformed_evidence_fan_available`, `test_malformed_evidence_bools_reject_off` |

## 5. What is intentionally absent

- No real Controller A/B implementation, sample loop, stateful runtime,
  watchdog, command publisher, ACK sender, actuator call, threshold tuning or
  physical verification.
- No MQTT/DB/GPIO/FastAPI dependency.
- No hidden physical constant. Every number is caller config; test numbers are
  synthetic and carry no commissioning authority.
- No automatic OFF on a generic fault and no fault-specific incident policy;
  W11 owns that decision.

## 6. Limits

- Unit-level only: no physical sensor/actuator, no timing/deadline test, no
  broker/DB integration, no fault injection.
- The core is stateless; `current_state` is supplied to preserve hysteresis
  labeling and is not a full runtime state store.
- Stale-state behavior (FAULT/HOLD) is provisional pending W05; lockout/fault
  recovery is pending W10/W11.
