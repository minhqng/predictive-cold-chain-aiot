# Policy transition table v0 (W02)

**Scope:** proposed transition contract for the W03 policy core.
**Implementation target:** `evaluate_policy()` in `control/src/coldguard_control/policy.py`.
**Sources:** Doc 02 §2/§21–23/§37–38/§63 and Doc 05D §7/§19/§34.
**Status:** v0 design; thresholds/timings are required inputs to `PolicyConfig`.
Action values are policy intents, not actuator commands.

## 1. Gate order (normative)

```text
P0  BOOT / SELF_TEST                 -> no decision (precondition error)
P1  device_mode == FAULT_LOCKOUT     -> FAULT_LOCKOUT, HOLD
P2  control_electrical_anomaly       -> FAULT_LOCKOUT, HOLD
P3  hardware_safety_condition        -> FAULT_LOCKOUT, HOLD
P4  fault_active                     -> FAULT_LOCKOUT or FAULT, HOLD
P5  thermal INVALID / UNKNOWN        -> FAULT_LOCKOUT, HOLD
P6  thermal stale / missing age      -> FAULT, HOLD
P7  usable T at/above upper, or
    critical latched above lower     -> CRITICAL_PROTECTION, ON, Controller A
P8  device_mode == SAFE_LOCAL and
    not all exit requirements        -> SAFE_LOCAL, local hysteresis
P9  remote path untrusted            -> SAFE_LOCAL, local hysteresis
P10 thermal DEGRADED (fresh)         -> NORMAL, local hysteresis, predictive blocked
P11 predictive warning                -> PREEMPTIVE_COOLING or WATCH
P12 otherwise                         -> NORMAL, Controller A hysteresis
```

## 2. Transition table

`Source` is the previous decision state where the transition is state-dependent;
`any` means the gate applies regardless of the previous label. `HOLD` means no
new policy actuation request.

| ID | Source | Condition | Destination | Action | Reason code | Notes |
|---|---|---|---|---|---|---|
| TR-01 | any | `device_mode == FAULT_LOCKOUT` | `FAULT_LOCKOUT` | HOLD | supplied `fault_reason` (may be none) | Lockout is not cleared by this function |
| TR-02 | any | unexpected energization / control electrical anomaly | `FAULT_LOCKOUT` | HOLD | `CONTROL_ELECTRICAL_ANOMALY` | Doc 01 §22.4/23.4, Doc 02 §2.7 |
| TR-03 | any | characterized hardware safety stop asserted | `FAULT_LOCKOUT` | HOLD | none (detail names hardware safety) | PHY-SAFE-009 |
| TR-04 | any | active fault with lockout-class reason | `FAULT_LOCKOUT` | HOLD | that reason | Currently `CONTROL_ELECTRICAL_ANOMALY` |
| TR-05 | any | active fault, non-lockout | `FAULT` | HOLD | supplied reason (may be none) | Incident action deferred to W11 |
| TR-06 | any | thermal quality INVALID or UNKNOWN | `FAULT_LOCKOUT` | HOLD | `THERMAL_STATE_INVALID` | No trustworthy protection state |
| TR-07 | any | thermal age missing or > freshness bound | `FAULT` | HOLD | none (detail: stale state) | Predictive blocked; final W05 rule pending |
| TR-08 | any | usable representative T ≥ upper boundary | `CRITICAL_PROTECTION` | ON | `THRESHOLD_HIGH` | Controller A; prediction cannot override |
| TR-09 | `CRITICAL_PROTECTION` | usable T > lower boundary (latched) | `CRITICAL_PROTECTION` | ON | `THRESHOLD_HIGH` | Hysteresis latch until recovery boundary |
| TR-10 | `SAFE_LOCAL` | device mode is SAFE_LOCAL and ≥1 exit requirement missing | `SAFE_LOCAL` | local hysteresis | `NETWORK_UNAVAILABLE` / `BACKEND_UNAVAILABLE` / `AI_UNAVAILABLE`, or local threshold reason | `transition=None`, `safe_local_exit_missing` lists gaps |
| TR-11 | any online mode | broker disconnected beyond grace | `SAFE_LOCAL` | local hysteresis | `NETWORK_UNAVAILABLE` | Entry marker `SAFE_LOCAL_ENTER` if previous label was not SAFE_LOCAL |
| TR-12 | any online mode | backend unsynced, stale, untrusted sync, or untrusted command path | `SAFE_LOCAL` | local hysteresis | `BACKEND_UNAVAILABLE` | Same entry marker rule |
| TR-13 | any online mode | predictive enabled but prediction missing/stale/unhealthy | `SAFE_LOCAL` | local hysteresis | `AI_UNAVAILABLE` | Never reuse one old score |
| TR-14 | `SAFE_LOCAL` | all exit requirements satisfied; no qualifying prediction | `NORMAL` | local hysteresis (HOLD/OFF) | none or `THRESHOLD_RECOVERED` | `transition=SAFE_LOCAL_EXIT` |
| TR-15 | `SAFE_LOCAL` | all exit requirements satisfied; risk ≥ watch but not preemptive | `WATCH` | HOLD | `PREDICTED_CRITICAL` | Exit marker also set |
| TR-16 | `SAFE_LOCAL` | all exit requirements satisfied; risk ≥ preemptive and persistence met | `PREEMPTIVE_COOLING` | ON | `PREDICTED_CRITICAL` | Controller B; exit marker also set |
| TR-17 | `SAFE_LOCAL` | usable T ≥ upper boundary (gate P7 fires before exit) | `CRITICAL_PROTECTION` | ON | `THRESHOLD_HIGH` | Device mode may remain SAFE_LOCAL; the action is still local protection |
| TR-18 | `NORMAL` / `WATCH` / `PREEMPTIVE_COOLING` | usable T ≥ upper boundary | `CRITICAL_PROTECTION` | ON | `THRESHOLD_HIGH` | Controller A takes over immediately |
| TR-19 | `WATCH` / `NORMAL` | risk ≥ preemptive threshold and persistence ≥ required | `PREEMPTIVE_COOLING` | ON | `PREDICTED_CRITICAL` | Controller B; requires fresh READY prediction and trusted path |
| TR-20 | `NORMAL` / `PREEMPTIVE_COOLING` | risk ≥ watch but below preemptive or persistence not met | `WATCH` | HOLD | `PREDICTED_CRITICAL` | Advisory only |
| TR-21 | `WATCH` / `PREEMPTIVE_COOLING` | risk below watch threshold, state usable | `NORMAL` | local hysteresis | none | If T is inside the band and cooling is ON, the action is HOLD (keeps ON) |
| TR-22 | `CRITICAL_PROTECTION` | usable T ≤ lower boundary | `NORMAL` | OFF if applied ON, otherwise HOLD | `THRESHOLD_RECOVERED` (if OFF requested) | Leaves critical latch |
| TR-23 | `NORMAL` | applied ON and T ≤ lower boundary | `NORMAL` | OFF | `THRESHOLD_RECOVERED` | Normal hysteresis |
| TR-24 | `NORMAL` | inside hysteresis band, any applied legal state | `NORMAL` | HOLD | none | No threshold crossing; no new request |
| TR-25 | `NORMAL` | fresh DEGRADED quality with usable representative | `NORMAL` | local hysteresis | `SENSOR_DEGRADED` | Predictive blocked; A continues |

## 3. Actions at each destination (summary)

| State | Policy action (intent) | Who holds authority |
|---|---|---|
| `NORMAL` | HOLD, or OFF after recovery | Controller A |
| `WATCH` | HOLD | Controller A |
| `PREEMPTIVE_COOLING` | ON within the legal action family | Controller B, bounded by the gate |
| `CRITICAL_PROTECTION` | ON | Controller A |
| `FAULT` | HOLD; physical disposition is W11 | Controller A |
| `SAFE_LOCAL` | Local hysteresis HOLD/ON/OFF | Controller A |
| `FAULT_LOCKOUT` | HOLD; physical lockout output is hardware/W10 | Controller A |

## 4. SAFE_LOCAL entry and exit

### Entry (any one is sufficient)

1. Broker disconnected, or offline duration exceeds `broker_offline_grace_s`.
2. Backend state unsynchronized, older than `backend_state_max_age_s`, or
   marked untrusted.
3. Remote command path marked untrusted.
4. Predictive policy is enabled but the prediction is missing, not `READY`,
   stale beyond `prediction_max_age_s`, or version-invalid.

Entry sets `transition="SAFE_LOCAL_ENTER"` when the previous label was not
`SAFE_LOCAL`. The decision still uses local hysteresis, so local protection is
never suspended.

### Exit (all are required; Doc 02 §38, 05D §19)

```text
broker_connected
network_stable_s >= safe_local_exit_min_stable_s
backend_state_synced
backend_state_age_s <= backend_state_max_age_s
state_sync_trusted
remote_command_path_trusted
not stale_command_pending
fresh VALID thermal telemetry (age <= thermal_max_age_s)
prediction healthy/fresh if predictive policy is enabled
no active fault / electrical anomaly / hardware safety condition
```

`SAFE_LOCAL` exits to `NORMAL`, `WATCH` or `PREEMPTIVE_COOLING` depending on the
prediction, and only after every requirement holds. A reconnect alone never
satisfies `network_stable`, `state_sync_trusted` or the fresh-telemetry gate.
The exit gate is fail-closed on numerics: a non-finite (`NaN`/`±inf`) or
negative timing never counts as satisfied, because `NaN` comparisons are always
false and would otherwise make the gate look open. It is fail-closed on
booleans too: only exact `True` counts as connected/synchronized/trusted and
only exact `False` counts as no stale command or no critical fault. A truthy
`"false"` or a falsy `""`/`0` is reported as the relevant missing requirement.

## 5. Forbidden / impossible transitions in W03

- `FAULT_LOCKOUT` → any actuating state inside `evaluate_policy()`: lockout can
  only be cleared by the documented device recovery path, which this pure
  function does not implement.
- Prediction → `ON` while state is `FAULT`, `FAULT_LOCKOUT` or `SAFE_LOCAL`.
- `WATCH` → `ON` without passing the persistence gate.
- Any → `NORMAL` from `SAFE_LOCAL` while an exit requirement is missing.
- A remote command forcing SAFE_LOCAL exit (the validator has no such action).
- A model, DB, frontend or operator path to the actuator (see W01
  trust-boundary).

## 6. Known transition-table gaps

1. **Stale state**: TR-07 is a W03 policy choice (FAULT/HOLD). W05 must freeze
   the actual degraded/freshness fallback. No automatic OFF is claimed.
2. **FAULT action**: TR-05/HOLD may not be the best physical action for every
   fault; W11 D-W11-04 owns warn/block/force-OFF/local/lockout per fault.
3. **Recovery thresholds**: no recovery/clear rule for lockout/fault is defined
   here; reset semantics belong to W10/W11 and the device runbook.
4. **Timing values**: all grace, stability, freshness and persistence values are
   planned to be synthetic in W03 unit tests and must be frozen from characterization before use.
5. **Device-mode vs policy-label divergence**: `CRITICAL_PROTECTION` can be
   returned while the device mode is still `SAFE_LOCAL` (TR-17). The policy
   action is local protection; the mode transition remains the device's job.
