# Policy states v0 (W02)

**Scope:** the seven policy states required by Doc 05D §34 (D-W02-01), their
meaning, inputs and precedence.
**Implementation target:** `control/src/coldguard_control/policy.py`
(`PolicyState`, `PolicyInput`, `PolicyDecision`, `evaluate_policy`).
**Status:** v0 design contract for W03 implementation. No threshold, dwell or freshness
value is frozen; all come from `PolicyConfig`.

> **Device mode is not a policy state.** Doc 02 §2.1 defines device modes
> (`BOOT`, `SELF_TEST`, `ONLINE_NORMAL`, `ONLINE_DEGRADED`, `SAFE_LOCAL`,
> `FAULT_LOCKOUT`). Doc 02 §23 and 05D §34 define the policy-state vocabulary.
> The W03 design keeps them separate and consumes the mode as a precondition:
> `BOOT`/`SELF_TEST` should raise `PolicyPreconditionError`; `FAULT_LOCKOUT` as a
> device mode pins the policy to `FAULT_LOCKOUT`. This avoids inventing a
> mapping where none is documented.

## 1. States

| State | Meaning | Default intent | Controller | Typical reason | Predictive allowed? |
|---|---|---|---|---|---|
| `NORMAL` | Physical state usable; no critical boundary; no predictive intervention warranted (or degraded sensing with A continuing) | HOLD, or OFF at/below lower boundary | A (REACTIVE) | `THRESHOLD_RECOVERED`, `SENSOR_DEGRADED`, or none | Only if sensing is VALID and remote path trusted |
| `WATCH` | Fresh predictive risk is elevated but persistence/preemptive condition is not met | HOLD | A (REACTIVE) | `PREDICTED_CRITICAL` | Advisory only; no preemptive actuation |
| `PREEMPTIVE_COOLING` | Fresh, persistent predictive warning meets the configured threshold and persistence window | ON | B (PREDICTIVE) | `PREDICTED_CRITICAL` (+ `RISK_PERSISTENT` note) | Yes, only within the legal action family |
| `CRITICAL_PROTECTION` | Usable representative temperature is at/above the upper boundary, or critical protection is latched above the lower recovery boundary | ON | A (REACTIVE) | `THRESHOLD_HIGH` | Irrelevant; prediction cannot override |
| `FAULT` | A non-lockout fault is active, or physical state is stale beyond the freshness bound | HOLD (no new actuation) | A (REACTIVE) | supplied fault reason, or none for stale state | Blocked |
| `SAFE_LOCAL` | Remote intelligence/path is unavailable or untrusted and the documented exit requirements are not all satisfied | Local hysteresis (HOLD/ON/OFF) | A (REACTIVE) | `NETWORK_UNAVAILABLE`, `BACKEND_UNAVAILABLE`, `AI_UNAVAILABLE` | Blocked |
| `FAULT_LOCKOUT` | Safe actuation cannot be guaranteed, or the device is already locked out | HOLD (no new actuation) | A (REACTIVE) | `CONTROL_ELECTRICAL_ANOMALY`, `THERMAL_STATE_INVALID`, or supplied lockout reason | Blocked |

### Why `FAULT` and `FAULT_LOCKOUT` are separate

Doc 02 §2.7 distinguishes a condition that invalidates normal policy from a
condition where safe actuation cannot be guaranteed. 05D §3/§34 makes
`FAULT_LOCKOUT` an explicit policy state. The proposed W03 mapping is:

- control electrical anomaly, hardware safety stop, invalid/unknown critical
  thermal state, device mode `FAULT_LOCKOUT`, and a lockout-class fault reason →
  `FAULT_LOCKOUT`;
- other active faults and stale physical state → `FAULT`.

## 2. State precedence

```text
FAULT_LOCKOUT
  > CRITICAL_PROTECTION
    > FAULT
      > SAFE_LOCAL
        > PREEMPTIVE_COOLING
          > WATCH
            > NORMAL
```

This is the precedence of *safety effect*, not a claim that every state can be
reached from every other in one step. The actual gate order is in
`transitions.md`; for example `SAFE_LOCAL` is entered before predictive logic,
and `FAULT` is evaluated before `SAFE_LOCAL` so a local fault is not hidden by
a network problem.

## 3. Action vocabulary

`PolicyDecision.actuation_intent` is one of:

| Intent | Meaning at this layer |
|---|---|
| `HOLD` | No new policy request. Keep the currently applied legal state. This is not a hardware command. |
| `OFF` | Policy requests/confirms the OFF direction (safe direction). |
| `ON` | Policy requests energization within the characterized legal action family. W03 does not publish it. |

`HOLD` during `FAULT_LOCKOUT` means "no new actuation decision". The physical
lockout output (e.g. de-energized) is a hardware/W10 requirement, not proven by
this pure function. The command validator may still accept an OFF command in
lockout because OFF is the idempotent safe direction; it never accepts a new ON.

`ControllerId` records whether A or B produced the intent. `CRITICAL_PROTECTION`
and every fault/lockout decision are always Controller A: the model is advisory.

## 4. Inputs

| Input | Required semantics | Missing/gap handling |
|---|---|---|
| `device_mode` | Doc 02 §2.1 mode | BOOT/SELF_TEST → precondition error |
| `thermal.quality` | VALID/DEGRADED/INVALID/UNKNOWN | INVALID/UNKNOWN must not carry a value; VALID must carry value + age |
| `thermal.t_representative_c` | Already the configured representative (e.g. TMAX); W03 does not choose T1/T2/T3 | `PolicyConfig.representative_source` is mandatory |
| `thermal.age_s` | Age supplied by caller; core has no clock | Missing/stale → FAULT/hold |
| `applied_cooling` | Actual/assumed applied legal state | Used only for hysteresis and idempotent OFF |
| `remote.*` | Broker/backend trust, backend state age, stable-connectivity time, stale command flag | Untrusted → SAFE_LOCAL |
| `prediction` | READY health, versions, risk 0–1, age, horizon, persistence | Stale/unhealthy while predictive is enabled → SAFE_LOCAL / `AI_UNAVAILABLE` |
| `fault_active`, `fault_reason` | Fault evidence from W10/W11 | Plain fault → FAULT; lockout-class → LOCKOUT |
| `control_electrical_anomaly` | Unexpected OFF current / electrical anomaly | → LOCKOUT |
| `hardware_safety_condition` | Characterized hardware stop asserted | → LOCKOUT |
| `fan_available` | Not consumed by `evaluate_policy` in W03; enforced by the command validator for ON | Fan interlock remains a hardware requirement |
| `door_state` | OPEN/CLOSED/UNKNOWN; context only | Invalid value rejected; not a P0 interlock |
| `PolicyConfig` | All operating values | Missing required value → `ConfigError` |

**Numeric inputs fail closed.** Every numeric `PolicyConfig` value and every
numeric `PolicyInput` value must be finite (`NaN`/`±inf` rejected; `bool` is not
accepted where a number is expected). Python comparisons with `NaN` are always
false, so without this rule a `NaN` freshness/stability value would silently
look "fresh enough" and could let SAFE_LOCAL exit or a stale command appear
valid. `safe_local_exit_status()` is additionally fail-closed on its own: a
non-finite or negative timing never counts as a satisfied exit requirement.

**Enum fields are runtime-checked.** `device_mode`, `thermal.quality`,
`applied_cooling`, `current_state`, `electrical_quality`,
`prediction.health` and `fault_reason` must be actual enum members. Because the
vocabularies derive from `str`/`Enum`, a raw string such as `"FAULT_LOCKOUT"`
compares equal by value but fails every identity check; it is rejected with
`PolicyInputError` before any gate is evaluated, never coerced or reinterpreted.

**Boolean flags are runtime-checked.** `RemotePathView.broker_connected`,
`backend_state_synced`, `state_sync_trusted`,
`remote_command_path_trusted`, `stale_command_pending`, plus
`PolicyInput.fault_active`, `control_electrical_anomaly` and
`hardware_safety_condition`, must be actual `bool`; `fan_available` must be
`bool` or `None`. Python treats `"false"` (and any non-empty string) as truthy,
so without this rule a raw `"false"` could look connected/synchronized/trusted,
while `""` or `0` could silently clear a fault. Direct
`safe_local_exit_status()` is fail-closed as well: only exact `True`/`False`
satisfies a boolean requirement; malformed values are reported as missing.

## 5. Outputs

| Field | Meaning |
|---|---|
| `policy_version` | Traceability to the frozen config |
| `state` | One of the seven states |
| `actuation_intent` | HOLD/OFF/ON (advisory to the command layer) |
| `controller_id` | REACTIVE (A) or PREDICTIVE (B) |
| `reason_code` | Doc 02 §58–59 / 05D §28 vocabulary, or `OK` for an accepted command decision |
| `reason_detail` | Human-auditable explanation |
| `predictive_blocked` | Prediction must not influence action |
| `degraded_sensing` | A degraded-quality state was used (local protection still allowed if a usable representative exists) |
| `safe_local_exit_missing` | Stable names of unsatisfied exit requirements |
| `transition` | `SAFE_LOCAL_ENTER` / `SAFE_LOCAL_EXIT` / none |
| `notes` | Evidence details (e.g. persistence value) |

The decision object has no GPIO, broker, DB or actuator field. Turning a
decision into a command/actuation belongs to later work packages.

## 6. Explicitly open / not contracted

1. **Stale thermal state.** The proposed W03 rule returns `FAULT` + HOLD and blocks prediction.
   W05 (D-W05-02/03) owns the final degraded/freshness fallback semantics; no
   automatic OFF/ON rule is invented here.
2. **FAULT incident action.** Whether each fault warns, blocks prediction,
   forces OFF, keeps the local threshold or locks out is W11 D-W11-04. W03's
   HOLD means “no new decision”, not “verified best physical state”.
3. **All thresholds/timings.** Upper/lower temperature, thermal freshness,
   prediction freshness, persistence and safe-local stability are not frozen.
   W03 unit tests are planned to use synthetic values only.
4. **Degraded protocol.** One lost sensor may permit local protection with a
   valid representative; the exact representative set and degraded rules are
   Member A/W11 scope. W03 never treats `DEGRADED` as `VALID`.
5. **Device-mode transitions.** `SAFE_LOCAL` mode is exited by the device
   procedure; the policy only evaluates exit eligibility. The actual mode
   change and actuator handling are A/firmware scope.
