# W23 model card — actual W15 synthetic XGBoost candidate

> **Task:** B-W23-02 · **Artifact:** `coldguard-w15-synthetic-xgb-candidate-v1`
> **Evidence class:** `SYNTHETIC_SOFTWARE_CONTROL_ONLY` ·
> **Release eligibility:** `NON_DEPLOYABLE_CANDIDATE`.
>
> This card references the actual artifact produced in W15. W23 did not retrain,
> refit, re-optimize, re-calibrate or replace the model. The model bytes are
> unchanged. A completed card does **not** imply a release-approved model.

```text
MODEL_CARD = REPRODUCIBLY_DOCUMENTED

MODEL = SYNTHETIC_NON_DEPLOYABLE

CALIBRATION = RISK_SCORE_ONLY

REAL_LOCKED_TEST = NOT_RUN

PHYSICAL_MODEL_ACCEPTANCE = NOT_ISSUED
```

## 1. Artifact identity and native format

| Field | Value |
|---|---|
| Artifact ID | `coldguard-w15-synthetic-xgb-candidate-v1` |
| Primary native format | `model.ubj` |
| Secondary native format | `model.json` |
| `model.ubj` SHA-256 | `25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f` |
| `model.ubj` size | 46 433 bytes |
| `model.json` SHA-256 | `67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd` |
| `model.json` size | 32 683 bytes |
| Artifact manifest SHA-256 | `85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e` |
| Manifest schema | `coldguard-w15-model-artifact-v1` |
| Guarded interface | required; exact 28 ordered columns; raw native load prohibited |

The artifact manifest records all 16 canonical required metadata fields. W23
recomputed the SHA-256 of both model files from the actual bytes and they match
the W15 declaration exactly.

## 2. Ordered feature schema and hash

- Feature version: `CG-FEAT-1.0`
- Feature schema hash: `1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9`
- Ordered feature list hash: `98491993d95ba78292cc245d637a1832ebdfb80b1eb026361e39926fb331223c`
- Feature count: **28**

```text
T_chamber_max_c, T_chamber_min_c, T_chamber_mean_c, T_chamber_spread_c,
T_center_c, T_bottom_c, T_near_door_c,
rolling_mean_temperature_60s, rolling_std_temperature_60s,
rolling_min_temperature_60s, rolling_max_temperature_60s,
past_only_slope_c_per_min_60s, past_only_temperature_delta_60s,
past_only_spatial_spread_60s,
door_open, time_since_open, duration_so_far, count_past_60s,
applied_cooling, applied_duty, time_since_confirmed_applied_change,
cooling_voltage_v, cooling_current_a, cooling_power_w,
energy_counter_wh, past_integrated_cooling_energy_wh,
ambient_temperature_c, relative_humidity_pct
```

T1/T3/T4 are chamber-air probes; **T2 is the TEC hot side and is not a model
feature**. The guarded interface refuses missing, extra or reordered columns.
W23 did not change the feature order or label identity.

## 3. Model configuration and dependency versions

| Field | Value |
|---|---|
| Model family | XGBoost (`binary:logistic`, `tree_method = hist`) |
| Config version | `coldguard-xgb-v1-development-v1` |
| Config file SHA-256 | `01e48a55a116045233fd90da0d79bd0360e201c7ad310b60eb715b7b5009cb7a` |
| Canonical config SHA-256 | `4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a7660dd6481ee1f71a84` |
| Library version | xgboost 3.4.1 |
| Python | 3.12 |
| numpy / pandas / scikit-learn | 2.5.3 / 3.0.6 / 1.9.1 |
| Hyperparameters | `max_depth=3`, `learning_rate=0.05`, `n_estimators=60`, `subsample=1.0`, `colsample_bytree=1.0`, `reg_alpha=0.0`, `reg_lambda=1.0`, `scale_pos_weight=1.0`, `n_jobs=1`, `random_state=42` |
| Hyperparameter status | `DEVELOPMENT_CONFIG_CANDIDATE`; no W15 search was performed |
| Training code revision | `9027c469a82859b4eb2dcf5b4d8255bf1f59c641` (`GENERATION_BASE_NOT_DELIVERY_COMMIT`) |

## 4. Training dataset and eligibility class

| Field | Value |
|---|---|
| Dataset ID | `W11_EXPANDED_SYNTHETIC_GROUPED` |
| Fixture version | `coldguard-w11-synthetic-grouped-v1` |
| Fixture generator SHA-256 | `711bf4a0acd9913207c430a6188640afb2e9ff25feb156743de58a241ec6e837` |
| Data evidence class | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` |
| Development-only | yes |
| Locked test used | **no** |
| Training samples | 1 936 evaluable windows (480 positive / 1 456 negative) |
| Excluded | 960 censored windows |
| Training strategy | `UNWEIGHTED` (`scale_pos_weight = 1.0`) |

The artifact was refit on all 16 development runs after the grouped evaluation.
The reported metrics are the W11 grouped CV metrics of the A3b arm, not a new
score of the refit artifact and not a physical validation.

## 5. Run/group counts and independent units

| Unit | Count |
|---|---:|
| Development runs | 16 |
| Development pair groups (effective independent groups) | 8 |
| Grouped CV folds | 4 (6 train groups / 2 validation groups each; correlated folds) |
| Locked-test runs (membership only, unopened) | 4 (2 pairs) |
| Physical runs used in training | 0 |

Four correlated grouped folds are not four physical experiments. The statistical
unit for generalization is the run/pair group, not the feature window.

## 6. Target definition and horizon status

| Field | Value |
|---|---|
| Target spec | `coldguard-w11-development-label-v1` |
| Target definition | binary critical event in `(t, t+60 s]` on the development candidate label |
| Target status | `DEVELOPMENT_CANDIDATE_NOT_FROZEN` |
| Representative temperature | `DEVELOPMENT_CANDIDATE_NOT_SELECTED` |
| Critical threshold | not frozen (`boundary_c = null`) |
| Horizon | 60 s |
| Horizon status | `ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN` |

The 60 s value is an engineering reference inherited from W11. It is not a
physically justified primary horizon and is not a measured physical early-warning
time.

## 7. Operating threshold and persistence

| Field | Value |
|---|---|
| Operating threshold | 0.5 |
| Threshold status | `ILLUSTRATIVE_NOT_FROZEN` |
| Warning persistence | `NOT_FROZEN` (no `k`) |

The threshold is not a frozen operational policy and does not define a valid
warning rule.

## 8. Calibration and score interpretation

W14 selected `RISK_SCORE_ONLY`. The artifact output is a **risk score**, not an
empirically calibrated probability:

- no calibration model was fitted for the plant;
- no percentage-risk or `P(critical within H)` wording is permitted;
- the W14 synthetic calibration diagnostic is a software control
  (`SYNTHETIC_SOFTWARE_CONTROL_ONLY`) and is not a validated real probability
  curve;
- reliability bins are not interpretable (perfect synthetic separation, 3 empty
  bins).

## 9. Existing grouped CV metrics and evidence class

W11 A3b grouped CV, 4 folds, seed 42, A3B arm:

| Metric | Value |
|---|---:|
| OOF Average Precision (`UNWEIGHTED`) | 1.0000 |
| OOF Average Precision (`TRAIN_FOLD_CLASS_WEIGHT`) | 1.0000 |
| Fold AP range | 1.0000–1.0000 |
| Event recall | 1.0000 |
| False warning episodes per hour | 0.0000 |
| Missed critical events | 0 |
| Confusion (TP/FP/TN/FN) | 480 / 0 / 1 456 / 0 |

Evidence class: `SYNTHETIC_SOFTWARE_CONTROL_ONLY`. These are saturated software
controls. Synthetic AP = 1.0 is **not** a physical AP, does not establish
physical predictive value, and must not be quoted as real-world early warning.

## 10. A1/A2/A3 findings

| Component | Verdict | Interpretation |
|---|---|---|
| A1 — one temperature vs three role-qualified chamber-air probes | `SOFTWARE_VERIFIED` | software probe set difference on the synthetic fixture |
| A2 — thermal vs thermal + door | `SOFTWARE_VERIFIED` | synthetic comparison with a scenario-identification trap |
| A3 — thermal vs thermal + electrical/applied | `SOFTWARE_VERIFIED`; physical effect `NOT_ESTABLISHED` | both arms saturate; electrical block is run-invariant in the fixture |

A1/A2/A3 are software verifications on the synthetic fixture. They are not
physical model-selection evidence and do not prove thermal or electrical
forecasting.

## 11. Model inspection and shortcut risks

The W15 native model inspection (diagnostic only) found that the fitted candidate
has 60 trees and 60 splits:

```text
tree_count           = 60
total_split_count    = 60
used_feature_count   = 1
used_feature_ids     = [time_since_open]
split_thresholds     = [60.0 s]
unused_feature_count = 27
```

Every split is on `time_since_open` at a 60 s threshold. All other 27 features,
including all eight electrical/applied-state features, are unused in the fitted
artifact. The artifact is therefore a door-time rule induced by the synthetic
fixture, not a learned thermal/electrical early-warning function.

Split usage is a native model diagnostic, **not causal feature importance** and
not evidence about a real plant. Known shortcut risks recorded by W15:
controller-action proxy through applied-state features, cumulative energy
features acting as run-age/scenario identifiers, PWM-sampled branch power being
meter-dependent, and branch energy not being whole-system energy.

## 12. Offline/online parity evidence

| Field | Value |
|---|---|
| W17 offline replay anchors | 784 |
| Compared anchors | 783 (1 refused as stale input) |
| Feature comparisons passed | 783 / 783 |
| Prediction comparisons passed | 783 / 783 |
| Max feature deviation | 0.0 |
| Max score deviation | 0.0 |
| Mutation proof | detected (0.5 °C feature mutation) |
| Shadow trace | 783 records, `SYNTHETIC_SOFTWARE_CONTROL_ONLY` |
| Live shadow | `LIVE_SHADOW_NOT_ESTABLISHED` |

This is offline replay parity on synthetic traces. It is not live shadow
acceptance, not a physical deployment and not a Controller B enablement.

## 13. Robustness and degraded-input limitations

| Situation | Behaviour |
|---|---|
| Stale/untrusted thermal sensor | thermal feature missing per registry rule; no silent fill |
| PZEM `UNKNOWN`/`INVALID`/`DEGRADED` | electrical feature missing; never zero and never `VALID` |
| Counter reset/rollover | `MISSING_COUNTER_RESET`; no negative consumption |
| Power gap > 5 s | integrated energy missing; never bridged |
| Door state `UNKNOWN` | door feature missing, never `CLOSED` |
| Feature order/identity mismatch | guarded artifact refuses prediction |
| Model byte hash mismatch | guarded loader refuses the artifact |
| Missing evidence / unsupported domain | risk score is not a claim of validity |

W21 bounded on-device injections (one session, output stage compiled out) are
diagnostic only. Real model robustness under sensor loss, real PZEM failure
diagnosis and fault-detection accuracy are `NOT_ESTABLISHED`.

## 14. Intended use

- Offline software-control experiments on the W11 synthetic fixture.
- Risk-score ranking with explicit `risk_score` semantics.
- A future shadow-inference candidate **only after all release gates** are
  satisfied.

## 15. Prohibited use

- Physical Controller B actuation or any hardware command.
- Calibrated-probability, percentage-risk or `P(critical)` wording.
- Public reliability, accuracy or early-warning-superiority claims.
- Final A/B comparison or any physical-benefit claim.
- Registration, deployment or activation in Member C’s backend.
- Use as evidence of physical thermal or electrical forecasting.

## 16. Release gates not yet satisfied

1. Admissible real grouped development population.
2. Physically justified primary horizon and frozen critical target.
3. Frozen operational policy (threshold and persistence).
4. Score/calibration decision with a real calibration population.
5. Accepted model/feature identity and a reproducible artifact.
6. W16 locked test, evaluated once without retuning (currently `NOT_RUN`,
   `holdout_opened = false`).
7. C/D shadow and authorization gates.
8. Team-lead release authorization; Gate G4 `NOT_READY`; Gate G5
   `NOT_ESTABLISHED`.

## 17. Exact artifact/source checksums

| Artifact | SHA-256 |
|---|---|
| `ml/reports/W15/model/model.ubj` | `25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f` |
| `ml/reports/W15/model/model.json` | `67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd` |
| `ml/reports/W15/model/model-manifest-W15.json` | `85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e` |
| `ml/reports/W15/w15-manifest.json` | `3f1a16939e1c16345e9948eb109085d123d3e57a57717132b0ab9c2d89d5eafa` |
| `ml/reports/W15/A3-model-inspection-W15.json` | `ec6746d0155597f6233f436284acb0cf0a218a6e2a96dd44455f53fd070363a6` |
| `ml/reports/W15/hyperparameter-freeze-candidate-W15.json` | `07d6b6d1efe119e9b33937c44850486382ec5b89adb0008b093bbe380b4a0aa6` |
| `ml/feature-registry-v1.yaml` | `f1c716a61c1d5c8eeaf0ff6e9596320c6df0bb47bce11ece0e67c038c72ffdbb` |
| `ml/xgb-v1-config.yaml` | `01e48a55a116045233fd90da0d79bd0360e201c7ad310b60eb715b7b5009cb7a` |
| `ml/uv.lock` | `dae6cae255b6cdd7c8ca0ded7e902124c0dac467215f309feb45642ad649e5a5` |

## 18. No-mutation statement

W23 did not modify `model.ubj`, `model.json` or their manifest. It did not
regenerate the model under a different version while claiming the same SHA. It
did not change feature order or label identity, did not create a
release-approved `model-rc/` folder, and did not open the W16 locked test. The
artifact remains `NON_DEPLOYABLE_CANDIDATE`.
