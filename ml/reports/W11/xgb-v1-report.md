# W11 grouped XGBoost benchmark report

> W11 software report. Synthetic training is a software control, never physical evidence. The real A capture is invalid and Gate B is RED; no real model was trained and no real benchmark exists.

## 1. Scientific verdicts

| Domain | Status |
|---|---|
| W11 software | GREEN |
| Synthetic training | PASSED |
| Grouped evaluation framework | VERIFIED_BY_TESTS |
| Physical Gate B | RED |
| Real predictive dataset | NOT_READY |
| Real XGBoost benchmark | NOT_ESTABLISHED |
| Real baseline comparison | NOT_ESTABLISHED |
| Real EWT | NOT_ESTIMABLE |
| Real AIW | NOT_ESTIMABLE |

## 2. Population and provenance

- Dataset: `W11_EXPANDED_SYNTHETIC_GROUPED`
- Fixture version: `coldguard-w11-synthetic-grouped-v1`
- Provenance: `SYNTHETIC_SOFTWARE_CONTROL_ONLY`
- W10 parent manifest: `reports/W10/feature-manifest-W10.json` SHA-256 `3706cbb7c59c74e5f21e3575ed49121fcd404454b8ca4250328063c07755fad2`
- W08 Gate B manifest: `reports/W08/gate-b-manifest-W08.json` SHA-256 `1dde8ea3d62b4cf7ba8a409108ab3f99b1170656880571c8fa6515af639babd6`
- Feature registry SHA-256: `1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9`
- Model config SHA-256: `4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a7660dd6481ee1f71a84`
- Repository revision at generation: `c6b28678430ab575902a09be4b32bc327c72afcb`
- Test runs (untouched): CG-W11-S1-001, CG-W11-S1-002, CG-W11-S2-001, CG-W11-S2-002
- W10 held-out synthetic test pair remains untouched

The W11 expanded fixture is independently generated with deterministic synthetic sources. It does not borrow, inspect or modify the W10 held-out synthetic test pair or any real physical data.

## 3. Grouped development split and CV

- Grouping key: run_id + pair_id (one effective group per pair)
- Effective independent groups: 8
- Folds: 4 (seed 42)
- Development samples: 1936 (480 positive, 1456 negative)
- Censored label exclusions: 960
- Untrusted label exclusions: 0
- Bound-preserving order: grouped split → causal feature windows → labels → train-only transforms → fit → grouped evaluation.

Fold inventory:

| Fold | Train runs | Validation runs | Train groups | Validation groups |
|---|---|---|---|---|
| F1 | CG-W11-S1-003, CG-W11-S1-004, CG-W11-S1-007, CG-W11-S1-008, CG-W11-S1-009, CG-W11-S1-010, CG-W11-S2-003, CG-W11-S2-004, CG-W11-S2-007, CG-W11-S2-008, CG-W11-S2-009, CG-W11-S2-010 | CG-W11-S1-005, CG-W11-S1-006, CG-W11-S2-005, CG-W11-S2-006 | W11-PAIR-003, W11-PAIR-004, W11-PAIR-007, W11-PAIR-008, W11-PAIR-009, W11-PAIR-010 | W11-PAIR-005, W11-PAIR-006 |
| F2 | CG-W11-S1-003, CG-W11-S1-004, CG-W11-S1-005, CG-W11-S1-006, CG-W11-S1-009, CG-W11-S1-010, CG-W11-S2-003, CG-W11-S2-004, CG-W11-S2-005, CG-W11-S2-006, CG-W11-S2-009, CG-W11-S2-010 | CG-W11-S1-007, CG-W11-S1-008, CG-W11-S2-007, CG-W11-S2-008 | W11-PAIR-003, W11-PAIR-004, W11-PAIR-005, W11-PAIR-006, W11-PAIR-009, W11-PAIR-010 | W11-PAIR-007, W11-PAIR-008 |
| F3 | CG-W11-S1-004, CG-W11-S1-005, CG-W11-S1-006, CG-W11-S1-007, CG-W11-S1-008, CG-W11-S1-010, CG-W11-S2-004, CG-W11-S2-005, CG-W11-S2-006, CG-W11-S2-007, CG-W11-S2-008, CG-W11-S2-010 | CG-W11-S1-003, CG-W11-S1-009, CG-W11-S2-003, CG-W11-S2-009 | W11-PAIR-004, W11-PAIR-005, W11-PAIR-006, W11-PAIR-007, W11-PAIR-008, W11-PAIR-010 | W11-PAIR-003, W11-PAIR-009 |
| F4 | CG-W11-S1-003, CG-W11-S1-005, CG-W11-S1-006, CG-W11-S1-007, CG-W11-S1-008, CG-W11-S1-009, CG-W11-S2-003, CG-W11-S2-005, CG-W11-S2-006, CG-W11-S2-007, CG-W11-S2-008, CG-W11-S2-009 | CG-W11-S1-004, CG-W11-S1-010, CG-W11-S2-004, CG-W11-S2-010 | W11-PAIR-003, W11-PAIR-005, W11-PAIR-006, W11-PAIR-007, W11-PAIR-008, W11-PAIR-009 | W11-PAIR-004, W11-PAIR-010 |

## 4. Label and feature identity

- Label spec: `coldguard-w11-development-label-v1`
- Horizon H: 60 s (development candidate; not frozen)
- Label identity: `{"boundary_c": null, "frozen_at": null, "horizon_s": 60.0, "representative_temperature": "DEVELOPMENT_CANDIDATE_NOT_SELECTED", "spec_version": "coldguard-w11-development-label-v1"}`
- Feature count: 28
- Explicit allowlist: `T_chamber_max_c`, `T_chamber_min_c`, `T_chamber_mean_c`, `T_chamber_spread_c`, `T_center_c`, `T_bottom_c`, `T_near_door_c`, `rolling_mean_temperature_60s`, `rolling_std_temperature_60s`, `rolling_min_temperature_60s`, `rolling_max_temperature_60s`, `past_only_slope_c_per_min_60s`, `past_only_temperature_delta_60s`, `past_only_spatial_spread_60s`, `door_open`, `time_since_open`, `duration_so_far`, `count_past_60s`, `applied_cooling`, `applied_duty`, `time_since_confirmed_applied_change`, `cooling_voltage_v`, `cooling_current_a`, `cooling_power_w`, `energy_counter_wh`, `past_integrated_cooling_energy_wh`, `ambient_temperature_c`, `relative_humidity_pct`
- Excluded diagnostic feature: `T_tec_hot_side_c`
- Missing values become NaN; an UNKNOWN electrical quality is never zero-filled.

## 5. Model and score semantics

- Model family: XGBoost 3.4.1
- Parameters: `{"colsample_bytree": 1.0, "learning_rate": 0.05, "max_depth": 3, "n_estimators": 60, "n_jobs": 1, "objective": "binary:logistic", "random_state": 42, "reg_alpha": 0.0, "reg_lambda": 1.0, "subsample": 1.0, "tree_method": "hist"}`
- Imbalance strategies: UNWEIGHTED, TRAIN_FOLD_CLASS_WEIGHT
- Score semantics: `risk_score` — not a calibrated probability
- Calibration: `NOT_PERFORMED`
- Risk operating threshold: 0.5 (illustrative development point)
- Package versions: `{"numpy": "2.5.3", "pandas": "3.0.6", "python": "3.12", "scikit_learn": "1.9.1", "xgboost": "3.4.1"}`

## 6. Fold results

| Fold | Strategy | Train groups | Validation groups | Train +/- | Validation +/- | AP | Undefined reason |
|---|---|---|---|---|---|---|---|
| F1 | UNWEIGHTED | 6 | 2 | 360/1092 | 120/364 | 1.0000 |  |
| F2 | UNWEIGHTED | 6 | 2 | 360/1092 | 120/364 | 1.0000 |  |
| F3 | UNWEIGHTED | 6 | 2 | 360/1092 | 120/364 | 1.0000 |  |
| F4 | UNWEIGHTED | 6 | 2 | 360/1092 | 120/364 | 1.0000 |  |
| F1 | TRAIN_FOLD_CLASS_WEIGHT | 6 | 2 | 360/1092 | 120/364 | 1.0000 |  |
| F2 | TRAIN_FOLD_CLASS_WEIGHT | 6 | 2 | 360/1092 | 120/364 | 1.0000 |  |
| F3 | TRAIN_FOLD_CLASS_WEIGHT | 6 | 2 | 360/1092 | 120/364 | 1.0000 |  |
| F4 | TRAIN_FOLD_CLASS_WEIGHT | 6 | 2 | 360/1092 | 120/364 | 1.0000 |  |

### Out-of-fold summary

| Strategy | OOF status | OOF AP | Fold AP values | Fold instability | Reason |
|---|---|---|---|---|---|
| UNWEIGHTED | DEFINED | 1.0000 | 1.0000, 1.0000, 1.0000, 1.0000 | 0.0000 |  |
| TRAIN_FOLD_CLASS_WEIGHT | DEFINED | 1.0000 | 1.0000, 1.0000, 1.0000, 1.0000 | 0.0000 |  |

Per-fold values are retained; no best-looking fold is presented as the benchmark.

> The expanded fixture is a deterministic software control. A perfect or near-perfect AP here reflects scenario-identifying synthetic features such as door state and thermal excursion, not physical predictive performance. No synthetic AP is a ColdGuard result.

## 7. Imbalance comparison

Both strategies reuse the same folds, feature order and label population. Class weights are derived only from the training group labels in each fold; a single-class training fold refuses fit rather than inventing a weight.

| Strategy | Fit folds | Refused folds | Weight formula |
|---|---|---|---|
| UNWEIGHTED | 4 | 0 | scale_pos_weight = 1.0 |
| TRAIN_FOLD_CLASS_WEIGHT | 4 | 0 | scale_pos_weight = train_negative / train_positive |

## 8. B0/B1 versus XGBoost

The comparison uses the same eligible development runs, physical source identity, event-time domain, label/critical-event definition, horizon, warning-episode policy and censoring rules. The methods have different semantics: B0 is a raw threshold criterion, B1 is a reactive hysteresis ON state, and XGBoost is a learned risk score. Their AP values are not an equal-semantics contest; the metric unit is named below.

| Method | Fold | Eligible samples | Event denominator | Sample AP | Event precision | Event recall | Matched | Unmatched | Missed | EWT |
|---|---|---|---|---|---|---|---|---|---|---|
| B0_THRESHOLD | F1 | 484 | 2 | 0.9874 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| B1_HYSTERESIS | F1 | 484 | 2 | 0.6897 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| B0_THRESHOLD | F2 | 484 | 2 | 0.9886 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| B1_HYSTERESIS | F2 | 484 | 2 | 0.6953 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| B0_THRESHOLD | F3 | 484 | 2 | 0.9889 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| B1_HYSTERESIS | F3 | 484 | 2 | 0.6840 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| B0_THRESHOLD | F4 | 484 | 2 | 0.9891 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| B1_HYSTERESIS | F4 | 484 | 2 | 0.6953 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| XGBOOST_V1_UNWEIGHTED | F1 | 484 | 2 | 1.0000 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| XGBOOST_V1_UNWEIGHTED | F2 | 484 | 2 | 1.0000 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| XGBOOST_V1_UNWEIGHTED | F3 | 484 | 2 | 1.0000 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| XGBOOST_V1_UNWEIGHTED | F4 | 484 | 2 | 1.0000 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| XGBOOST_V1_TRAIN_FOLD_CLASS_WEIGHT | F1 | 484 | 2 | 1.0000 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| XGBOOST_V1_TRAIN_FOLD_CLASS_WEIGHT | F2 | 484 | 2 | 1.0000 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| XGBOOST_V1_TRAIN_FOLD_CLASS_WEIGHT | F3 | 484 | 2 | 1.0000 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |
| XGBOOST_V1_TRAIN_FOLD_CLASS_WEIGHT | F4 | 484 | 2 | 1.0000 | 1.0000 | 1.0000 | 2 | 0 | 0 | NOT_ESTIMABLE |

- Sample unit: feature anchor window.
- Event unit: warning episode versus prescribed critical event.
- B0/B1 are reused from W09; their state machines are not reimplemented.
- EWT is `NOT_ESTIMABLE` here for a benchmark-specific reason: these rows are synthetic and carry no authoritative physical, non-intervened trajectory with frozen warning and reactive definitions supplying both anchors in one trusted event-time domain. Command/ACK/thermal latency is not an EWT requirement.
- AIW separately remains `NOT_ESTIMABLE` because no complete measured command, ACK and thermal response latency chain exists.
- An episode is counted by onset before the evaluation cutoff; warning inputs after the cutoff are truncated, never used to establish the onset. Critical events beyond the cutoff are right-censored, not silently dropped.
- False-warning rates use trusted all-channel-VALID exposure, not the elapsed span from zero. A zero or untrusted denominator is undefined, never zero.
- When any evaluable run has untrusted exposure, false-warning density and event recall stay undefined; event precision remains over observed episodes only.
- A warning episode is one operational event, not one positive sample.
- Eventless and censored populations remain undefined, never zero.

## 9. Real physical data

- Gate B: `RED`
- Eligible real runs: 0
- Real development split: `NOT_FEASIBLE`
- Training executed: `NO`
- Benchmark status: `NOT_FEASIBLE`
- Real XGBoost benchmark: `NOT_ESTABLISHED`
- Real baseline comparison: `NOT_ESTABLISHED`
- Real EWT: `NOT_ESTIMABLE` (`EWT_UNAVAILABLE_NO_QUALIFIED_COMMON_TRAJECTORY`) — no eligible physical non-intervened event population and no authoritative frozen warning/reactive timing pair.
- Real AIW: `NOT_ESTIMABLE` (`AIW_UNAVAILABLE_MEASURED_LATENCY_CHAIN_MISSING`) — no complete measured system/physical latency chain.
- Refusal reasons: PHYSICAL_GATE_RED, RUN_IDENTITY_UNRESOLVED, DEVICE_IDENTITY_MISSING, ABSOLUTE_EVENT_TIME_NOT_EVIDENCED, REAL_DEVELOPMENT_SPLIT_NOT_FEASIBLE, NO_ADMITTED_DEVELOPMENT_SPLIT_MEMBERS, COMPLETENESS_POLICY_NOT_FROZEN, A_LEDGER_NOT_VALID, NOT_ELIGIBLE_FOR_PREDICTIVE_DATASET, ADMISSION_STAGE_BELOW_PREDICTIVE_DATASET, HARDWARE_CONFIG_NOT_VERIFIED, CALIBRATION_NOT_VERIFIED, TIME_DOMAIN_NOT_ABSOLUTE_UTC, CLOCK_SYNC_NOT_EVIDENCED, SCENARIO_NOT_CERTIFIED, BLOCKING_RUN_VALIDATION_FAILURE, INSUFFICIENT_ADMITTED_REAL_RUNS_FOR_GROUPED_CV

The A W09 capture is diagnostic only. Gate B RED is not permission to train on its rows, and no synthetic metric is promoted into physical evidence.

## 10. Leakage audit

| Result | Count |
|---|---|
| `BLOCKED_BY_MISSING_EVIDENCE` | 1 |
| `NOT_APPLICABLE` | 1 |
| `PASS` | 15 |

Full record: `leakage-audit-W11.md`.

## 11. Artifacts

```text
ml/xgb-v1-config.yaml
ml/src/coldguard_ml/xgb_benchmark.py
ml/src/coldguard_ml/grouped_evaluation.py
ml/src/coldguard_ml/leakage_audit.py
ml/scripts/xgb-benchmark-W11.py
ml/reports/W11/cv-fold-manifest.yaml
ml/reports/W11/xgb-v1-report.md
ml/reports/W11/leakage-audit-W11.md
ml/reports/W11/benchmark-manifest-W11.json
ml/reports/W11/fold-metrics-W11.csv
ml/reports/W11/baseline-comparison-W11.csv
ml/reports/W11/model-synthetic-smoke.ubj
ml/reports/W11/model-synthetic-smoke.json
```

| Artifact | SHA-256 |
|---|---|
| `baseline-comparison-W11.csv` | `e6dcd3bbafe8ac8868fe4fe613b9261409f352b5b70071d2b45b7b11a4a10918` |
| `cv-fold-manifest.yaml` | `702623f12e04cdc0162cb5517e691fbf62cee85d25b0c651a267ff46cc91e8c6` |
| `fold-metrics-W11.csv` | `f475049385183481bbe4341fe590cb00b2be4b6b66e967b4b9882e90a9f3083e` |
| `leakage-audit-W11.md` | `71903c0114d0cdfa70aae1cd508df89ce124c6e119237e31aca05bafa89a36aa` |
| `model-synthetic-smoke.json` | `82e487a99ba93dad4e192000f826dacc6d62377316672ba4f010ba9f1368cebc` |
| `model-synthetic-smoke.ubj` | `2665c214fa52c3ba43c0c845be7269c50e10989c047245c9d1e44297fbec20d2` |

## 12. Limitations

- deterministic synthetic fixture; its data-generating process does not approximate real thermal performance
- no real physical data is borrowed, inspected or modified
- the W10 held-out synthetic test pair is untouched by W11
- metrics are software controls, not a ColdGuard predictive-science result
- The synthetic AP is not a ColdGuard predictive-science result.
- No real calibration, EWT, AIW, false-warning burden or baseline improvement is established.
- EWT and AIW have different evidence contracts. A future EWT value would not establish AIW without a measured latency chain.
- W12 owns the consolidated benchmark and Gate G3 report; W11 does not implement W12 conclusions.
