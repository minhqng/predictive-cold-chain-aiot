# W14 calibration feasibility and output decision

**Task:** B-W14-03 / B-W14-04 · **Layer:** `coldguard-w14-group-safe-calibration-v1`
**Scientific evidence class: `SYNTHETIC_SOFTWARE_CONTROL_ONLY` for the diagnostics.**
**Decision: `RISK_SCORE_ONLY`.**

> The model output remains a `risk_score`. It is not an empirically calibrated
> probability for the plant. No percentage-risk wording is permitted.

## 1. Decision record (B-W14-04)

| Field | Value |
|---|---|
| Decision | `RISK_SCORE_ONLY` |
| Reasons | `CALIBRATION_BLOCKED_NO_REAL_ELIGIBLE_DEVELOPMENT_POPULATION`, `CALIBRATION_BLOCKED_TARGET_OR_HORIZON_NOT_FROZEN`, `CALIBRATION_BLOCKED_SYNTHETIC_SOFTWARE_CONTROL_ONLY`, `CALIBRATION_BLOCKED_RELIABILITY_BINS_NOT_INTERPRETABLE` |
| Missing requirements | real eligible population, real independent groups, frozen label identity, frozen horizon, disjoint fit/calibration/evaluation groups, disjoint pair lineage, interpretable reliability, estimable Brier, estimable discrimination, frozen model/feature identity, non-synthetic evidence |
| Product requirement for probability wording | **No.** The canonical contract makes probability wording conditional, not mandatory. |

### Product-facing contract (frozen output semantics)

1. The model output is a `risk_score`, not an empirically calibrated probability.
2. No percentage-risk wording and no claim such as "72% chance of critical
   temperature within H" is permitted.
3. Display and interpretation must state that the score is an uncalibrated
   decision statistic.
4. Any later transition to probability wording requires a new evidence-backed
   decision.

### Freeze scope

Frozen: the **output semantics** of the current development/release candidate
(`risk_score`, no probability wording).

Not frozen: the primary prediction horizon, the final physical model, any
probability-calibration model, W15 operating threshold/persistence, and the W16
locked-test result.

## 2. Why calibration is blocked

| Question | Live answer | Evidence |
|---|---|---|
| Is probability wording required by the product contract? | No; it is a conditional permission after calibration evidence | Doc 00 §6.4; Doc 02 §19.7; Doc 03 §58–60; Doc 05B §2.3; Doc 05C §79; code exposes `risk_score` only |
| Is there sufficient independent calibration evidence? | No; 0 real predictive-eligible runs | W13 manifest `reconciliation.predictive_eligible_runs = 0` |
| Are both classes present in appropriate folds? | Only in the synthetic control | W11 synthetic fixture; no real population |
| Can fitting and evaluation use disjoint grouped data? | Only in the synthetic control | 4 outer folds, 2 calibration + 2 evaluation + 4 model-fit groups per fold |
| Can reliability bins be interpreted? | No | perfect synthetic separation, 2 non-empty bins, 3 empty, correlated windows |
| Does calibration improve reliability without unacceptable degradation? | Not demonstrable for the plant; synthetic Brier improves only under perfect separation | this report |

Additional blockers: the label identity is a development candidate
(`DEVELOPMENT_CANDIDATE_NOT_FROZEN`), the horizon is not frozen
(`NOT_FROZEN`), the critical threshold is unfrozen, and Gate G3 remains
**NO-GO / FIX DATA**. A synthetic calibration experiment never qualifies as
probability evidence.

## 3. Method reviewed (official scikit-learn 1.9.1 documentation)

Documentation was checked on 2026-11-10 against the installed scikit-learn
**1.9.1**.

- **Reliability / calibration curve** — `sklearn.calibration.calibration_curve`
  bins `[0, 1]` and "bins with no samples … will not be returned, thus the
  returned arrays may have less than n_bins values." Empty bins are therefore
  reported explicitly, never imputed.
- **Brier score** — `sklearn.metrics.brier_score_loss` defines the binary score
  as the mean squared difference; with `scale_by_half='auto'` the binary output
  is the plain MSE in `[0, 1]`. This report uses `pos_label=1` and the binary
  `[0, 1]` scale.
- **Sigmoid calibration** — selected as the only fitted candidate. It is
  monotone and stable on small calibration groups.
- **Isotonic calibration** — refused. The official guidance is that isotonic is
  "not recommended when the number of calibration samples is too low (≪1000)".
  The synthetic calibration subsets are 484 windows.
- **`CalibratedClassifierCV`** — in 1.9.1 its `fit` has no `groups` parameter;
  `cv=None` uses the default 5-fold `StratifiedKFold` over rows. ColdGuard
  cannot assume that splitter respects run groups, so the default CV is not
  used.
- **Already-fitted estimator** — the model is wrapped in `FrozenEstimator` and
  calibrated with `CalibratedClassifierCV(estimator=FrozenEstimator(model),
  method="sigmoid", cv=None)`. The official page states: "The user has to take
  care manually that data for model fitting and calibration are disjoint."
  W14 enforces that disjointness and records it per fold.
- **AP** — `average_precision_score` is step-wise, not interpolated. A
  single-class evaluation keeps AP `None` with an explicit reason; it is never
  replaced by zero.

## 4. Group-safe software control

The synthetic control reuses the frozen W11 development population and a
predeclared model (UNWEIGHTED XGBoost, W11 parameters). No model or calibrator
tuning was performed.

| Fold | Model-fit groups | Calibration groups | Evaluation groups | Fit / cal / eval samples | Cal +/- | Eval +/- |
|---|---|---|---:|---:|---:|
| F1 | 003, 004, 007, 010 | 008, 009 | 005, 006 | 968 / 484 / 484 | 120/364 | 120/364 |
| F2 | 004, 005, 009, 010 | 003, 006 | 007, 008 | 968 / 484 / 484 | 120/364 | 120/364 |
| F3 | 005, 006, 007, 008 | 004, 010 | 003, 009 | 968 / 484 / 484 | 120/364 | 120/364 |
| F4 | 003, 005, 007, 009 | 006, 008 | 004, 010 | 968 / 484 / 484 | 120/364 | 120/364 |

All three sets are pairwise disjoint; pair lineage is disjoint; each
development group is evaluation-only exactly once. The locked test pair is never
read.

## 5. Quantitative diagnostics

### Per-fold diagnostics

| Fold | Raw Brier | Calibrated Brier | Delta (cal − raw) | Raw AP | Calibrated AP | Non-empty bins | Empty bins | Perfect separation |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| F1 | 0.000544 | 0.0000223 | −0.0005218 | 1.0000 | 1.0000 | 2 | 3 | yes |
| F2 | 0.000544 | 0.0000223 | −0.0005218 | 1.0000 | 1.0000 | 2 | 3 | yes |
| F3 | 0.000544 | 0.0000223 | −0.0005218 | 1.0000 | 1.0000 | 2 | 3 | yes |
| F4 | 0.000544 | 0.0000223 | −0.0005218 | 1.0000 | 1.0000 | 2 | 3 | yes |

### Pooled out-of-fold diagnostics

| Metric | Raw | Calibrated |
|---|---:|---:|
| Brier (binary, `pos_label=1`, `[0, 1]`) | 0.0005441225824452 | 0.0000223039815209 |
| Average precision | 1.0000 | 1.0000 |
| Independent evaluation groups | 8 | 8 |

Reliability bins (uniform, 5 bins; calibrated scores; pooled OOF):

| Bin | Count | Positive | Negative | Groups | Mean score | Observed positive fraction | Interpretable |
|---|---:|---:|---:|---:|---:|---:|---|
| [0.0, 0.2) | 1456 | 0 | 1456 | 8 | 0.002732 | 0.0000 | yes |
| [0.2, 0.4) | 0 | 0 | 0 | 0 | — | — | empty |
| [0.4, 0.6) | 0 | 0 | 0 | 0 | — | — | empty |
| [0.6, 0.8) | 0 | 0 | 0 | 0 | — | — | empty |
| [0.8, 1.0] | 480 | 480 | 0 | 8 | 0.991796 | 1.0000 | yes |

The group count of 8 per bin does **not** establish independent support: each
pair contributes both an S1 and an S2 run, and the fixture's windows are highly
correlated. Perfect separation means the reliability curve is a two-point
artefact of the generator, so the overall reliability interpretation is
`NOT_INTERPRETABLE`.

Undefined metrics are never zero: empty bins are absent from the curve and
counted explicitly (3 empty), and a single-class evaluation would produce
`None` with `CALIBRATION_EVALUATION_UNDEFINED_SINGLE_CLASS`.

## 6. Negative cases and deterministic refusals

| Case | Behaviour | Reason code |
|---|---|---|
| Single-class calibration subset | calibrator is not fitted | `CALIBRATION_REFUSED_SINGLE_CLASS_CALIBRATION_SUBSET` |
| Sparse independent-group support | bin marked not interpretable | `CALIBRATION_RELIABILITY_SPARSE_GROUP_SUPPORT` |
| Overlapping fit/calibration/evaluation groups | refused before fit | `CALIBRATION_REFUSED_OVERLAPPING_FIT_CALIBRATION_EVALUATION_GROUPS` |
| Shared A/B pair across calibration and evaluation | refused before fit | `CALIBRATION_REFUSED_SHARED_PAIR_LINEAGE` |
| Target/horizon unavailable/frozen | probability claim blocked | `CALIBRATION_BLOCKED_TARGET_OR_HORIZON_NOT_FROZEN` |
| Perfectly separable synthetic scenario | no probability claim | `CALIBRATION_PERFECT_SEPARATION_SYNTHETIC_SCENARIO` |
| Scores outside `[0, 1]` | refused | `CALIBRATION_REFUSED_SCORE_OUTSIDE_UNIT_INTERVAL` |
| NaN/infinite scores | refused | `CALIBRATION_REFUSED_NON_FINITE_SCORE` |
| Missing label trust | evaluation refused | `CALIBRATION_REFUSED_UNTRUSTED_LABEL_POPULATION` |
| Changed feature/model identity | refused | `CALIBRATION_REFUSED_FEATURE_OR_MODEL_IDENTITY_MISMATCH` |
| Non-synthetic fixture | refused | `CALIBRATION_REFUSED_NON_SYNTHETIC_FIXTURE` |
| Any predeclared W11 model parameter drift | refused | `CALIBRATION_REFUSED_FEATURE_OR_MODEL_IDENTITY_MISMATCH` |
| Default row-level/stratified CV | refused | `CALIBRATION_CV_NOT_GROUP_SAFE` |
| Isotonic below ~1000 calibration samples | refused | `CALIBRATION_ISOTONIC_REFUSED_INSUFFICIENT_CALIBRATION_SAMPLES` |
| Locked test enters calibration/threshold | refused | `CALIBRATION_REFUSED_LOCKED_TEST_ACCESS` |

## 7. What would change the decision

A future `CALIBRATED_PROBABILITY_SUPPORTED` decision requires **all** of:

1. a real eligible development/calibration population with both classes;
2. frozen label identity and frozen primary horizon (D/A);
3. grouped model-fit, calibration and evaluation sets with disjoint run and
   pair lineage;
4. a reported Brier and reliability curve with non-sparse independent-group
   support and honest uncertainty;
5. frozen model and feature identity;
6. an untouched locked test;
7. a new evidence-backed decision record.

Owners: **Member A** for physical runs, absolute time/clock, run identity and
calibration traceability; **Member D** for the critical threshold and policy
semantics; **Member C** for the network command path and latency evidence;
**Leader** for PR #95/merge decisions; **Member B** for the real grouped
calibration evaluation after those inputs exist.

## 8. Limitations

- Synthetic observations can validate the software path only; they cannot
  validate probability reliability for the real plant.
- Perfect separation makes the synthetic Brier improvement non-informative.
- Four outer folds reuse correlated development groups; no significance claim.
- Reliability bins contain correlated windows, not independent events.
- The synthetic control does not establish a physical calibration model and is
  not promotable to release.

## 9. Reproduction and binding

```bash
cd ml
uv run --locked --python 3.12 python scripts/w14-ablation-W14.py
```

| Binding | Value |
|---|---|
| W14 manifest | `w14-manifest.json` SHA-256 `e4a0263ead067a10df8d23ffc2bb10d6e750c88e515153fd6f637c733077357d` |
| Base revision | `824a5389c29ade0e56ecef7ef21eb35c2a379a7b` |
| Calibration candidate family | sigmoid only |
| Isotonic refusal | `<1000` calibration samples |
| Group policy | explicit disjoint groups; no default CV |
| Brier definition | binary, positive class `y=1`, `[0, 1]` mean squared difference |
| Calibration diagnostics | `calibration-summary-W14.json` SHA-256 `c1da43b0125429cb39e5f917a3824c73e826a8ccb4e38d5b436556051d66e96c` |
| Fold CSV | `calibration-folds-W14.csv` SHA-256 `58a565d6b692f80e3d7e9365c836528dff58da7f87719a3fbadd28ed20237ce3` |
| Bin CSV | `calibration-bins-W14.csv` SHA-256 `961a0f91aa4bb76f7d8c25f5b743d89127bfdbd5b8f07890b83a66c0c84004ec` |

## 10. Unresolved questions

- Does the real plant produce both classes in independent calibration groups?
  **Unknown; 0 eligible runs.**
- Is a sigmoid calibrator adequate for the real score distribution? **Not
  estimable.**
- Will D's critical threshold and A's door-to-critical evidence make the target
  and horizon freezable? **Pending A/C/D inputs, not a B decision.**
