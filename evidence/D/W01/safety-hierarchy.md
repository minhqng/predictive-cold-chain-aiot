# ColdGuard safety hierarchy (W01)

**Status:** v0 design baseline. The pure policy core is a later stacked W03 deliverable; W01 contains no control code.
**Owner:** Member D.
**Date:** 2026-10-19.
**Sources:** Doc 00 §2.7, §4.3, §4.7, §8, §12; Doc 01 §19, §22–25, §28, §39;
Doc 02 §2, §21–24, §31–32, §37–38, §58–59, §63, §82; Doc 05D §7, §19, §27–28,
§33–35.

> This document is design evidence, not a safety certification. No physical
> actuator was commanded to produce it. Thresholds contemplated for later policy code are
> supplied by the caller and are not yet frozen from characterization.

## 1. Authority chain

```text
physical safety interlocks / default-off
  > local deterministic protection (device, no network required)
    > reactive control (Controller A, local thresholds + hysteresis)
      > predictive control (Controller B, advisory risk score)
        > optimization / efficiency (never safety-authoritative)
```

The chain is lexical, not a voting scheme. A lower layer cannot outvote a
higher one:

- If local protection says **energize**, a predictive "do not cool" advice
  cannot suppress it.
- If a hard fault or an unusable physical state exists, no risk score can
  create actuation permission.
- If the remote path is untrusted, only SAFE_LOCAL behavior is allowed until
  every documented exit requirement holds.

Source: Doc 00 §2.7; Doc 02 §21–23 and §82; Doc 05D §7.

## 2. Proposed decision order for the W02/W03 policy gate

This is the design order for the later pure policy implementation. W01 records
the authority contract only; no policy function is included in this branch.

| # | Gate | Result | Why it is here |
|---|---|---|---|
| 1 | Boot/self-test | no decision (`PolicyPreconditionError`) | Actuator must stay OFF before the system is online (Doc 02 §2.2–2.3) |
| 2 | Device already in `FAULT_LOCKOUT` | `FAULT_LOCKOUT`, HOLD | Lockout requires the documented recovery path, not a new decision |
| 3 | Control electrical anomaly | `FAULT_LOCKOUT`, HOLD | Actuation cannot be guaranteed safe (Doc 01 §22.4/23.4, Doc 02 §2.7) |
| 4 | Characterized hardware safety stop | `FAULT_LOCKOUT`, HOLD | Hardware stop dominates software advice (PHY-SAFE-009) |
| 5 | Active fault | `FAULT`, HOLD (lockout class → `FAULT_LOCKOUT`) | Fault invalidates normal policy; incident action for each fault is W11 |
| 6 | Thermal quality INVALID/UNKNOWN | `FAULT_LOCKOUT`, HOLD | No trustworthy physical state; lockout rather than a guess (PHY-SAFE-008) |
| 7 | Thermal state stale | `FAULT`, HOLD, predictive blocked | No new actuation on stale data (SW-SAFE-004); final fallback rule is W05 |
| 8 | Temperature at/above upper boundary | `CRITICAL_PROTECTION`, ON, Controller A | Local protection always wins |
| 9 | Remote path untrusted / prediction unhealthy | `SAFE_LOCAL`, local hysteresis | Deterministic local behavior (Doc 02 §37–38) |
| 10 | Degraded thermal sensing | `NORMAL`, local hysteresis, predictive blocked | Member A's degraded protocol; prediction is not permitted on missing evidence |
| 11 | Fresh persistent predictive warning | `PREEMPTIVE_COOLING` (Controller B) or `WATCH` | Predictive action only after the frozen warning contract exists |
| 12 | Otherwise | `NORMAL` / Controller A hysteresis | Baseline reactive behavior |

Implementation and unit-test evidence are delivered in the later stacked W03
change; they are not part of this W01 branch.

Gate numbering here is an order description only; `W02/transitions.md` carries
the authoritative P0–P12 gate list (it splits the SAFE_LOCAL-mode exit check from
the remote-untrusted check).

## 3. What each layer may and may not authorize

| Layer | May | May **not** |
|---|---|---|
| Physical interlock / hardware stop | Remove energy, latch a stop condition | Be bypassed by firmware policy |
| Device local policy | Reject any command, hold a legal state, enter `SAFE_LOCAL`/`FAULT_LOCKOUT` | Invent thresholds without a frozen config |
| Controller A | Request OFF/ON within the characterized action family | Override a fault, lockout or invalid measurement |
| Controller B (model) | Produce a versioned, fresh advisory risk score | Publish a command, call GPIO, bypass validation, or act on stale/invalid features |
| Backend | Authenticate, authorize, validate, expire, deduplicate, audit | Bypass the device safety gate or write GPIO |
| Broker | Route authenticated messages under ACL | Authorize actuation or synthesize commands |
| Database | Store state, commands, ACKs and audit evidence | Issue control commands |
| Frontend | Request an intent through backend authn/authz | Hold device credentials or direct actuator access |
| Operator | Authenticate, inspect, request a permitted action | Direct GPIO/actuator access |

## 4. Non-negotiable invariants

The test names below describe planned W03 verification targets; W01 does not
include or claim execution of those tests.

1. **No model → GPIO path.** The model output type is an advisory view consumed
   by policy; `PolicyDecision` has no GPIO/transport field. A source-scan test
   fails if the core imports MQTT, DB, GPIO, web, serial or clock modules
   (`test_core_imports_no_transport_db_gpio_or_web_modules`).
2. **Boot is OFF.** Policy evaluation is undefined in `BOOT`/`SELF_TEST`; the
   hardware/board layer must hold the actuator OFF (Doc 02 §2.2).
3. **No invalid measurement actuates.** `INVALID`/`UNKNOWN` thermal quality
   cannot carry a value and cannot authorize action; `VALID` without a value is
   rejected (`test_invalid_quality_must_not_carry_a_substituted_value`).
4. **Critical protection dominates prediction.** A temperature at/above the
   configured upper boundary yields `CRITICAL_PROTECTION` + Controller A even
   with a 0.99 fresh risk score
   (`test_critical_protection_beats_fresh_predictive_warning`).
5. **Fault dominates optimization.** An active fault yields `FAULT`/HOLD even
   with a fresh high-risk prediction
   (`test_plain_fault_beats_every_predictive_optimization`).
6. **Reconnect is not trust.** SAFE_LOCAL exit requires stable connectivity,
   reconciled backend state, fresh valid telemetry, no stale command, a trusted
   command path and no critical fault
   (`test_reconnect_alone_does_not_restore_remote_trust`).
7. **ACK is not physical proof.** `ACCEPTED` means only that the validator
   found no rejection reason; physical verification remains W04/W12 and is
   recorded as a separate state (Doc 02 §32.2).
8. **No silent ignore.** Every Doc 01 failure maps to DEGRADE, FALLBACK,
   LOCKOUT or NOT_CONTRACTED; `IGNORE` is not a member of the taxonomy enum.

## 5. Known limits of this W01 baseline

- Thresholds, hysteresis, freshness, dwell and duty bounds are **not frozen**.
  The later W03 policy package must require them through `PolicyConfig` and ship no numeric defaults.
- No hardware, broker, backend or database is part of this evidence. The
  security controls in `security-baseline-v0.md` are requirements with owners,
  not deployed claims.
- Control-task starvation, watchdog behavior and boot-time output level are
  hardware/firmware properties; W03 cannot test them. They remain open hazards
  with named owners.
- `FAULT` incident actions (force OFF vs hold) are explicitly deferred to W11
  D-W11-04. The proposed W03 `HOLD` is a conservative "no new actuation" decision,
  not a claim that every fault leaves the actuator in its best state.
