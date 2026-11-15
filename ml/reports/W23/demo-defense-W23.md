# W23 demo narrative and defense card

> **Task:** B-W23-05. The narrative explains the actual evidence, not an
> aspirational result. It must fit a realistic two-minute delivery.

```text
DEMO NARRATIVE = VERIFIED (content reviewed against W23 evidence)
TEAM REHEARSAL STATUS = NOT_EVIDENCED
```

## A. Two-minute script

> I’m Member B. I’ll separate what the model is, what it is not, and what the
> A/B experiment proved.
>
> **Dataset split.** We split by run and matched pair, never by telemetry row.
> The synthetic fixture has ten pairs: sixteen development runs in eight groups
> for grouped cross-validation, and two pairs held out as a locked test. Both
> arms stay on one side; overlapping windows would otherwise leak. The locked
> test is pre-registered and unopened.
>
> **Why XGBoost.** It is a bounded tabular candidate against threshold and
> hysteresis baselines, not automatically superior. A deep model was a documented
> NO-GO because no real development population justified it.
>
> **What it predicts.** The contract asks whether a representative temperature
> crosses a critical boundary within a horizon. The current label uses a
> sixty-second reference. That horizon is not physically frozen, the critical
> temperature is not frozen, and the output is a risk score, not a calibrated
> probability.
>
> **How early.** We cannot claim a measured early-warning time. Real EWT and AIW
> are not estimable without a qualified physical trajectory and a measured
> latency chain. Synthetic AP of one is a software control.
>
> **How actionable.** Not established. Threshold and persistence are
> illustrative, not frozen. Native inspection shows sixty trees and sixty splits,
> all on time-since-open at sixty seconds; the other twenty-seven features are
> unused. It is a synthetic door-time rule.
>
> **What A/B proved.** Nothing yet. The campaign is not authorized, the pair
> target is unfrozen, zero accepted pairs exist, and the W20 analysis is locked.
> The statistics engine is toy-verified only. W21 is one diagnostic session with
> the actuator output stage compiled out, not a Controller B benefit.
>
> So: reproducible software evidence, a documented synthetic model, and a
> pre-registered lock. No deployable model, no physical validation, no physical
> A/B improvement.

## B. Claim/evidence defense card

| # | Claim | Evidence | Class | Status |
|---:|---|---|---|---|
| 1 | Splits are by run and matched pair, both arms on one side | W11 fold manifest (`702623f1…`), W11 manifest (`855c5beb…`), leakage probes (`future_mutation`, `grouped_disjoint`, `pair_preservation`, `locked_test`) | `DETERMINISTIC_SOFTWARE_VERIFICATION` | VERIFIED |
| 2 | XGBoost is a bounded development candidate, not automatically superior | W11/W12/W15 reports; mandatory B0/B1 baselines; W15 deep-model `NO-GO` | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` | DOCUMENTED |
| 3 | Target is a binary critical-event contract with a 60 s engineering reference horizon | `coldguard-w11-development-label-v1`; W15 model manifest | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` | NOT_FROZEN |
| 4 | Output is a risk score, not a probability | W14 decision `RISK_SCORE_ONLY`; model manifest `calibration_status` | `METADATA_ONLY_VERIFICATION` | FROZEN SEMANTICS |
| 5 | Real EWT/AIW are not estimable | W13/W14/W22 reports; W22 closed-loop EWT refusal | `NOT_ESTIMABLE` | BLOCKED BY PHYSICAL EVIDENCE |
| 6 | The fitted artifact uses only `time_since_open` (60 trees/splits, 60 s) | `A3-model-inspection-W15.json` (`ec6746d0…`) | `DETERMINISTIC_SOFTWARE_VERIFICATION` | OBSERVED |
| 7 | Threshold and persistence are not frozen | W15 model manifest (`ILLUSTRATIVE_NOT_FROZEN`, `NOT_FROZEN`) | `METADATA_ONLY_VERIFICATION` | NOT_FROZEN |
| 8 | Synthetic AP = 1.0 is a software control | W11/W15 validation evidence, `not_physical_evidence = true` | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` | DOCUMENTED |
| 9 | Physical A/B has proven nothing | W20 `ANALYSIS_PREFLIGHT_BLOCKED`; 0 accepted pairs; pair target unfrozen | `MISSING_REQUIRED_EVIDENCE` | NOT_RUN |
| 10 | Paired statistics engine is toy-verified only | W22 manifest 56/56 probes, 21/21 reference checks, toy fixtures | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` | SOFTWARE_VERIFIED |
| 11 | W21 on-device session is bounded diagnostic, not intervention | W21 manifest: 1 session, output `COMPILED_OUT`, TEC actuation `NONE` | `ON_DEVICE_SOFTWARE_INJECTION` | BOUNDED |
| 12 | Locked test remains unopened | W16 manifest `evaluation_status = NOT_RUN`, `holdout_opened = false`; W22 prior-layer hash | `METADATA_ONLY_VERIFICATION` | NOT_OPENED |

## C. Difficult questions and prepared answers

### 1. Why not random-row splits?

Because overlapping windows from one run are near-duplicates. A random row or
window split lets nearly identical samples cross train/validation and inflates
metrics. We split runs, and pair both arms together, before generating windows
(Doc 03 §46–47; W11 leakage probes).

### 2. Why Average Precision?

Impending-critical samples are rare, so accuracy and ROC can look acceptable
while precision on the positive class is poor. AP/PR focuses on the rare positive
class and is the canonical primary discrimination candidate (Doc 03 §52). AP is
not the only metric: recall, false-warning burden, missed events and EWT are
reported separately.

### 3. Why is `risk_score` not a probability?

W14 blocked calibration because there is no real eligible population, the target
and horizon are unfrozen, the only data is synthetic, and reliability bins are
not interpretable. Score-only mode is explicitly permitted when calibration is
not evidenced (Doc 03 §58–59). Percentage-risk wording requires a new,
evidence-backed calibration decision.

### 4. Why are EWT and AIW separate?

EWT is warning time relative to the reactive crossing. AIW subtracts the measured
system and physical response delays, so a positive EWT can still be too late to
act. AIW needs a measured latency chain; W13/W14 have no qualified chain
(Doc 03 §55–57).

### 5. Why is EWT not a final physical A/B effect?

They answer different questions and require different evidence. EWT is an
offline predictive-timing question on observational/reactive trajectories;
physical benefit is a paired Controller A/B outcome. A closed-loop B trajectory
also destroys the naive no-control counterfactual — the reactive crossing that
was prevented is unobserved, so it must not be invented (Doc 03 §40; W20 causal
boundary).

### 6. Why XGBoost instead of LSTM?

The data is small, tabular and grouped, with a mandatory deterministic baseline
comparison. W15 documented a deep-model NO-GO: zero predictive-eligible real
runs, no structured temporal failure of XGBoost, no concrete incremental
question, and no defensible data sufficiency. XGBoost is a bounded candidate, not
a claim of superiority (Doc 05B §18–19; W15).

### 7. Why does synthetic AP = 1.0 not prove a good model?

The fixture is deterministic and separable; both arms saturate. Native inspection
shows the model is a single-feature door-time rule. Saturated synthetic AP is a
software control, not physical predictive performance, and must never be quoted
as real-world accuracy.

### 8. Why does the current model use only `time_since_open`?

The synthetic scenario is separated by door-time, so 60 splits at a 60 s
threshold minimize the fixture loss. Split usage is a native model diagnostic,
not causal importance. This is a shortcut finding that argues against deploying
the artifact, not for it.

### 9. Why is there no final physical p-value or CI?

There is no authorized final campaign, no accepted physical pair, no admitted
outcome export, and the W20 analysis gate is locked. A p-value or CI computed
now would be either fabricated or computed from unauthorized/toy data. The W22
engine is ready and toy-verified only; the real analysis remains withheld.

### 10. What would invalidate the scientific conclusion?

Any of: a broken pair (non-matching initial state, contamination, reused run),
invalid calibration/clock/time provenance, leakage across partitions, locked-test
exposure, outcome-definition drift, unblinded or peeking analysis, missing or
selectively excluded pairs, or failure to reproduce the stated hash-bound
pipeline. A synthetic result relabelled as physical would also invalidate it.

### 11. What evidence is required to authorize Controller B?

Gate G4 and the D-owned safety envelope: locked predictive evidence,
interpretable AIW, shadow-capable inference, security baseline, `SAFE_LOCAL`,
reconnect/resynchronization, physical command/response verification, plant/dataset
stability, frozen model/feature/policy/threshold/persistence, and team-lead
release authorization. W23 does not grant any of these.

## D. Rehearsal status

| Item | Status |
|---|---|
| Narrative authored and reviewed against evidence | DONE (this document) |
| Two-minute timing at ~150–160 words/minute | ESTIMATED 1:51 at 160 wpm / 1:58 at 150 wpm (script 295 words) |
| Three full team rehearsals as requested by Doc 04 W23 | **NOT_EVIDENCED** |
| Human independent reproduction | **PENDING** |

No team rehearsal, human signature or external acceptance is invented. The
rehearsal count remains an open team action for W24.

## E. Forbidden claims check

The following statements are **not** made anywhere in this narrative and must not
be added:

- “The AI predicts critical temperature 60 seconds early.”
- “Controller B reduced thermal exposure by X%.”
- “`risk_score` is a probability.”
- “Synthetic AP = 1.0 proves a good model.”
- “The 60 s horizon is physically frozen.”
- “G4/G5 are accepted.”
- “Actuator verification passed” from the output-disabled W21 session.
- Any invented p-value, confidence interval, pair count, rehearsal or signoff.

## F. Binding sources

- `ml/reports/W23/dataset-card-W23.md`
- `ml/reports/W23/model-card-W23.md`
- `ml/reports/W23/figure-availability-W23.md`
- `ml/reports/W15/model/model-manifest-W15.json`
- `ml/reports/W15/A3-model-inspection-W15.json`
- `ml/reports/W16/locked-test-manifest-W16.json`
- `ml/reports/W20/w20-manifest.json`
- `ml/reports/W21/w21-manifest.json`
- `ml/reports/W22/w22-manifest.json`
