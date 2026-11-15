# W15 — prediction value versus diagnosis value of electrical observation

**Task:** B-W15-02 · **Layer:** `coldguard-w15-electrical-ablation-v1`
**Classification: `SOFTWARE_ONLY_EVIDENCE`.**

This assessment separates two questions that must not be conflated:

- **Track P — predictive usefulness:** does electrical/applied-state input improve
  warning before a future thermal event on an admissible, non-predictively-intervened
  trajectory?
- **Track D — diagnosis / actuator observability:** can electrical observation help
  determine whether requested/applied cooling corresponds to an actual electrical or
  thermal response?

## 1. Track P — predictive usefulness

**Question.** Do electrical and applied-control features improve the ability to warn
before a future thermal event on an admissible non-predictively-intervened
trajectory?

**Evidence available in W15.**

| Requirement | Status |
|---|---|
| Leakage-safe feature availability | Software-verified: all features are causal at t; future-injection probes pass |
| True impending-critical labels | Synthetic only (`coldguard-w11-development-label-v1`, H = 60 s reference) |
| Grouped development support | Synthetic: 16 runs / 8 pair groups, 480 positive / 1456 negative windows |
| Matched A3 comparison | Complete: identical population, folds, labels and hyperparameters |
| Event-level operational behaviour | Synthetic: event recall 1.0, 0 false warnings/h, 0 missed events in both arms |
| Non-intervened trajectory | Synthetic S1/S2 fixture only; no real eligible trajectory |
| Real predictive-eligible runs | **0** |
| Real primary horizon / critical target | **Not frozen** |

**Result.** On the synthetic grouped fixture, adding the declared electrical/applied
feature set changed OOF AP by 0.0000 (1.0000 → 1.0000) under the fixed W11 protocol.
The A3a thermal/context arm already saturates the fixture. The fixture's electrical
block is run-invariant and every electrical feature has univariate scenario AUC 0.5.
The cumulative energy features are run-age proxies (Spearman 1.0 with anchor time).
Model inspection shows the refit A3b artifact splits only on `time_since_open`
(60/60 splits); every electrical feature is unused. The zero delta is a fixture
shortcut/saturation result, not a predictive-effect estimate.

**Conclusion.** `PREDICTION VALUE: NOT_ESTABLISHED`.

The A3 comparison verifies software wiring and isolation, not a physical predictive
benefit. It does not support the statement "electrical features improved
prediction". No real intervention-free trajectory exists, so intervention-created
counterfactual contamination cannot be assessed.

## 2. Track D — diagnosis and actuator observability

**Question.** Can electrical observation help determine whether requested/applied
cooling corresponds to actual electrical or thermal response?

**What W15 actually provides.**

1. **State observability.** The frozen registry separates:
   - `requested_cooling` (controller request; not admitted to A3),
   - `applied_cooling` / `applied_duty` (POWER_PATH applied state),
   - `cooling_voltage_v` / `cooling_current_a` / `cooling_power_w` (PZEM branch response),
   - thermal trajectory (chamber-air response).

2. **Consistency checking.** `assess_actuator_electrical_response` classifies one
   observed sample into:
   - `APPLIED_STATE_UNKNOWN`,
   - `RESPONSE_UNVERIFIABLE`,
   - `NO_APPLIED_COMMAND`,
   - `APPLIED_WITH_ELECTRICAL_RESPONSE`,
   - `APPLIED_WITHOUT_ELECTRICAL_RESPONSE`,
   - `ELECTRICAL_RESPONSE_WITHOUT_APPLIED_COMMAND`.

   This is a contract-level consistency check. It never claims that an applied
   command is a verified actuation, and it never claims that current/power is a
   thermal response.

3. **Missingness safety.** `UNKNOWN`/`INVALID` electrical quality produces missing
   PZEM values, never zero or VALID. A counter reset is reported as
   `MISSING_COUNTER_RESET`; no negative consumption is created. A discontinuity or
   gap refuses the affected integrated-energy value.

4. **Separation from thermal confirmation.** W15 does **not** implement or validate a
   real thermal-response detector. Distinguishing "electrical power flowed" from
   "the chamber cooled" remains a measured thermal-response question.

**What cannot be established.**

- No empirical fault labels, anomaly rates or detector accuracy exist.
- No qualified real PZEM development population exists.
- PWM-sampled branch power is meter-dependent; PWM characterization is an A-owned
  W16 precondition before PZEM power/energy may be used as primary evidence; branch
  energy is not whole-system energy.
- A live electrical response is not proof of successful cooling.
- Diagnosis success would not automatically improve future-event prediction.

**Conclusion.** `DIAGNOSIS VALUE: SOFTWARE_ONLY`.

The available engineering interface is real; the empirical diagnosis benefit on the
physical rig is `NOT_ESTABLISHED`.

## 3. Decision

```text
PREDICTION VALUE:   NOT_ESTABLISHED
DIAGNOSIS VALUE:    SOFTWARE_ONLY
OVERALL:            SOFTWARE_ONLY_EVIDENCE
```

Separate evidence classes are retained; they are not collapsed into one verdict.

## 4. Explicitly unsupported claims

- "Electrical features improve early prediction."
- "A3b is equivalent to A3a because both reach AP 1.0."
- "Electrical features have zero physical value."
- "The actuator is electrically verified."
- "A current reading proves thermal cooling."
- "Diagnosis success implies predictive benefit."
- "The model is calibrated or ready for deployment."

## 5. Binding

- W15 manifest SHA-256: `3f1a16939e1c16345e9948eb109085d123d3e57a57717132b0ab9c2d89d5eafa`
- A3 report: `A3-report.md`
- Electrical audit: `A3-electrical-audit-W15.csv`
- Adversarial probes: `A3-adversarial-probes-W15.json`
- Scientific class: `SYNTHETIC_SOFTWARE_CONTROL_ONLY`

## 6. Unresolved questions

- Does a real qualified electrical population exist and does it separate actuator
  faults from healthy cooling? **Not established.**
- Which PZEM/PWM sampling corrections are valid on the as-built branch? **Not
  established.**
- Is the controller-action shortcut dominant on real Controller-A trajectories?
  **Untested.**
