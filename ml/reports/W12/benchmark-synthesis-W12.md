# W12 benchmark synthesis and Gate G3 readiness

**Software, synthetic benchmark validity and physical Gate G3 readiness are three different decisions.**

| Verdict | Status |
|---|---|
| W12 software | `GREEN` |
| Synthetic benchmark synthesis | `VERIFIED_BY_TESTS` |
| Physical Gate B | `RED` |
| Real grouped benchmark | `NOT_ESTABLISHED` |
| Real event metrics | `NOT_ESTIMABLE` |
| Real EWT | `NOT_ESTIMABLE` |
| Real AIW | `NOT_ESTIMABLE` |
| Gate G3 | `NO-GO / FIX DATA` |

## 1. Source pack

W12 reads W04–W11 contracts and artifacts as immutable inputs. Every W11 artifact hash is verified before synthesis. No A/C/D source or evidence is modified.

## 2. B-W12-01 — Grouped benchmark synthesis

The independent unit is the pair/run group, not the feature window.
W11 contributes 8 pair groups, 16 runs, 4 grouped folds and 1936 correlated feature windows. Synthetic AP=1.0 is a software-control result and does not show physical superiority.

See `grouped-metrics-W12.csv` for every fold value and summary row.

## 3. B-W12-02 — False warnings and missed events

W09 episode matching is reused. The synthetic operational table is in `event-operational-summary-W12.csv`; real false-warning burden, missed-event rate and event recall remain `NOT_ESTIMABLE` because zero eligible physical runs exist.

| Property | Synthetic population | Real physical population |
|---|---|---|
| Mathematical result available | yes, synthetic only | no eligible events |
| Scientific result supported | no physical claim | `NOT_ESTIMABLE` |

## 4. B-W12-03 — Initial EWT

EWT and AIW are separated. Synthetic timing cases demonstrate positive, negative, zero, missing-anchor, cross-run, cross-clock and intervention refusal behavior under `SYNTHETIC_TIMING_CONTRACT_TEST_ONLY`. Real EWT and AIW remain `NOT_ESTIMABLE` for different reasons. See `ewt-assessment-W12.csv`.

## 5. B-W12-04 — Feature-importance diagnostics

Fold-scoped XGBoost gain is reported in `feature-importance-W12.csv`. The top family in these fold models is `door` with feature `time_since_open`. Allowed conclusion: in this synthetic fixture these features were used by the model under the recorded version/configuration. Forbidden conclusion: these features physically cause critical cold-chain events. A door-timing or scenario-identifying feature is evidence of synthetic source identification, not thermal causality. No SHAP, no locked test, no causal claim.

## 6. B-W12-05 — Gate G3

**Decision: `NO-GO / FIX DATA`**

Hard blockers: `G3-A-PHYSICAL-PLANT`, `G3-B-GROUPED-DATASET`, `G3-B-XGB-BENCHMARK`, `G3-D-CONTROLLER-A`, `G3-D-COMMAND-VERIFY`, `G3-C-PLATFORM-BACKUP`, `G3-TEAM-APPROVAL`

The full matrix is in `gate-g3-evidence-matrix-W12.csv`; the decision report is `gate-g3-W12.md`.

## 7. Cross-milestone evidence integrity

- W04 admission remains authoritative: no eligible real run.
- W05 duplicate-view refusal and W06 clock/identity alignment remain preserved in the W08/W09/W10 chain.
- W07 independent-run counting, W08 Gate B RED and W09 event provenance are not rewritten.
- W10 feature causality/source binding and W11 grouped split/model provenance are verified by hash.
- No synthetic positive test substitutes for a missing physical source.

## 8. Verification and limitations

- Full W04–W11 regression suite is run after W12.
- Artifact hashes and deterministic replay are checked.
- No locked physical P3 dataset or test outcome is read.
- No PR is merged, retargeted or approved by this report.

## B-W12-02 operational synthesis

| Method | Fold | Units | Episodes | Matched | Unmatched | Missed | Event precision | Event recall | False/run | False/hour | Trusted h | Provenance |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| B0_THRESHOLD | F1 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| B0_THRESHOLD | F2 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| B0_THRESHOLD | F3 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| B0_THRESHOLD | F4 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| B1_HYSTERESIS | F1 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| B1_HYSTERESIS | F2 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| B1_HYSTERESIS | F3 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| B1_HYSTERESIS | F4 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| XGBOOST_V1_TRAIN_FOLD_CLASS_WEIGHT | F1 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| XGBOOST_V1_TRAIN_FOLD_CLASS_WEIGHT | F2 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| XGBOOST_V1_TRAIN_FOLD_CLASS_WEIGHT | F3 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| XGBOOST_V1_TRAIN_FOLD_CLASS_WEIGHT | F4 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| XGBOOST_V1_UNWEIGHTED | F1 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| XGBOOST_V1_UNWEIGHTED | F2 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| XGBOOST_V1_UNWEIGHTED | F3 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |
| XGBOOST_V1_UNWEIGHTED | F4 | episode/event/run/hour | 2 | 2 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 | 0.1333 | `SYNTHETIC_OPERATIONAL_EVALUATION_ONLY` |

One sustained warning episode counts once. Multiple warning samples do not create multiple events.

### Real physical population

| Metric | Status | Reason |
|---|---|---|
| Real false-warning burden | `NOT_ESTIMABLE` | NO_ELIGIBLE_PHYSICAL_S1_OR_S2_RUN |
| Real missed-event rate | `NOT_ESTIMABLE` | NO_ELIGIBLE_PHYSICAL_S1_OR_S2_RUN |
| Real event recall | `NOT_ESTIMABLE` | NO_ELIGIBLE_PHYSICAL_S1_OR_S2_RUN |

Zero qualified physical events do not create a zero rate; the rate is undefined.

### Unit statement

- `AP`: sample/window-level average precision; not event recall.
- `warning_episodes`: one contiguous warning interval counted once.
- `critical_events`: eligible observed critical events only.
- `exposure`: trusted all-channel-VALID hours, not elapsed span.
- `runs`: validation runs inside paired groups; independence is at group level, not run or window level.

## B-W12-03 EWT assessment

All timing rows below are synthetic contract demonstrations: `SYNTHETIC_TIMING_CONTRACT_TEST_ONLY`.

| Case | Status | EWT (s) | Reason code | Run identity | Clock domains |
|---|---|---:|---|---|---|
| CASE_A_POSITIVE_EWT | `ESTIMABLE` | 20.0000 | `EWT_ESTIMABLE` | SYNTHETIC-TIMING-RUN / SYNTHETIC-TIMING-RUN | BOOT_SCOPED_UPTIME / BOOT_SCOPED_UPTIME |
| CASE_B_NEGATIVE_EWT | `ESTIMABLE` | -10.0000 | `EWT_ESTIMABLE` | SYNTHETIC-TIMING-RUN / SYNTHETIC-TIMING-RUN | BOOT_SCOPED_UPTIME / BOOT_SCOPED_UPTIME |
| CASE_C_ZERO_EWT | `ESTIMABLE` | 0 | `EWT_ESTIMABLE` | SYNTHETIC-TIMING-RUN / SYNTHETIC-TIMING-RUN | BOOT_SCOPED_UPTIME / BOOT_SCOPED_UPTIME |
| CASE_D_NO_PERSISTENT_WARNING | `MISSING_WARNING` | undefined | `EWT_UNAVAILABLE_WARNING_OR_REACTIVE_ANCHOR_NOT_DEFINED` | SYNTHETIC-TIMING-RUN / SYNTHETIC-TIMING-RUN | BOOT_SCOPED_UPTIME / BOOT_SCOPED_UPTIME |
| CASE_E_NO_REACTIVE_CROSSING | `MISSING_REACTIVE_CROSSING` | undefined | `EWT_UNAVAILABLE_WARNING_OR_REACTIVE_ANCHOR_NOT_DEFINED` | SYNTHETIC-TIMING-RUN / SYNTHETIC-TIMING-RUN | BOOT_SCOPED_UPTIME / BOOT_SCOPED_UPTIME |
| CASE_F_CROSS_RUN | `REFUSED_CROSS_RUN` | undefined | `EWT_UNAVAILABLE_NO_QUALIFIED_COMMON_TRAJECTORY` | SYNTHETIC-TIMING-RUN / OTHER-RUN | BOOT_SCOPED_UPTIME / BOOT_SCOPED_UPTIME |
| CASE_G_CROSS_CLOCK | `REFUSED_CROSS_CLOCK` | undefined | `EWT_UNAVAILABLE_INCOMPATIBLE_CLOCK_DOMAIN` | SYNTHETIC-TIMING-RUN / SYNTHETIC-TIMING-RUN | BOOT_SCOPED_UPTIME / ABSOLUTE_UTC |
| CASE_H_INTERVENED | `INADMISSIBLE_INTERVENED_TRAJECTORY` | undefined | `EWT_UNAVAILABLE_INTERVENED_TRAJECTORY` | SYNTHETIC-TIMING-RUN / SYNTHETIC-TIMING-RUN | BOOT_SCOPED_UPTIME / BOOT_SCOPED_UPTIME |
| CASE_I_FIRST_VALID_ONSET | `ESTIMABLE` | 20.0000 | `EWT_ESTIMABLE` | SYNTHETIC-TIMING-RUN / SYNTHETIC-TIMING-RUN | BOOT_SCOPED_UPTIME / BOOT_SCOPED_UPTIME |

### Real timing status

| Metric | Status | Reason code | Reason |
|---|---|---|---|
| Real EWT | `NOT_ESTIMABLE` | `EWT_UNAVAILABLE_NO_QUALIFIED_COMMON_TRAJECTORY` | no eligible non-intervened physical event population and no authoritative frozen warning/reactive timing pair |
| Real AIW | `NOT_ESTIMABLE` | `AIW_UNAVAILABLE_MEASURED_LATENCY_CHAIN_MISSING` | no complete measured command/ACK/electrical/thermal latency chain |

EWT and AIW have different evidence contracts. An estimable EWT would not imply an actionable AIW.

Definitions:

- `warning_definition`: first valid persistent predictive warning.
- `persistence_definition`: w12-sustained-30s-v1 reviewed declaration.
- `reactive_definition`: first valid reactive criterion crossing.
- `ewt_formula`: EWT = t_reactive - t_predictive.
- `aiw_formula`: AIW = t_critical - t_warning - T_system - T_physical.
- `intervention_rule`: a predictively intervened trajectory is inadmissible for offline counterfactual EWT.

## B-W12-04 feature-importance diagnostics

Importance method: XGBoost gain, fold-scoped. No SHAP and no locked test.

| Feature | Family | Fold | Strategy | Gain | Share | Rank | Registry version | Interpretation limit |
|---|---|---|---|---:|---:|---:|---|---|
| `time_since_open` | door | F1 | UNWEIGHTED | 268.0602 | 1.0000 | 1 | CG-FEAT-1.0 | descriptive only |
| `T_bottom_c` | thermal | F1 | UNWEIGHTED | 0 | 0 | 2 | CG-FEAT-1.0 | descriptive only |
| `T_center_c` | thermal | F1 | UNWEIGHTED | 0 | 0 | 3 | CG-FEAT-1.0 | descriptive only |
| `T_chamber_max_c` | thermal | F1 | UNWEIGHTED | 0 | 0 | 4 | CG-FEAT-1.0 | descriptive only |
| `T_chamber_mean_c` | thermal | F1 | UNWEIGHTED | 0 | 0 | 5 | CG-FEAT-1.0 | descriptive only |
| `T_chamber_min_c` | thermal | F1 | UNWEIGHTED | 0 | 0 | 6 | CG-FEAT-1.0 | descriptive only |
| `T_chamber_spread_c` | thermal | F1 | UNWEIGHTED | 0 | 0 | 7 | CG-FEAT-1.0 | descriptive only |
| `T_near_door_c` | thermal | F1 | UNWEIGHTED | 0 | 0 | 8 | CG-FEAT-1.0 | descriptive only |
| `ambient_temperature_c` | environment | F1 | UNWEIGHTED | 0 | 0 | 9 | CG-FEAT-1.0 | descriptive only |
| `applied_cooling` | actuation | F1 | UNWEIGHTED | 0 | 0 | 10 | CG-FEAT-1.0 | descriptive only |
| `applied_duty` | actuation | F1 | UNWEIGHTED | 0 | 0 | 11 | CG-FEAT-1.0 | descriptive only |
| `cooling_current_a` | electrical | F1 | UNWEIGHTED | 0 | 0 | 12 | CG-FEAT-1.0 | descriptive only |
| `cooling_power_w` | electrical | F1 | UNWEIGHTED | 0 | 0 | 13 | CG-FEAT-1.0 | descriptive only |
| `cooling_voltage_v` | electrical | F1 | UNWEIGHTED | 0 | 0 | 14 | CG-FEAT-1.0 | descriptive only |
| `count_past_60s` | door | F1 | UNWEIGHTED | 0 | 0 | 15 | CG-FEAT-1.0 | descriptive only |
| `door_open` | door | F1 | UNWEIGHTED | 0 | 0 | 16 | CG-FEAT-1.0 | descriptive only |
| `duration_so_far` | door | F1 | UNWEIGHTED | 0 | 0 | 17 | CG-FEAT-1.0 | descriptive only |
| `energy_counter_wh` | electrical | F1 | UNWEIGHTED | 0 | 0 | 18 | CG-FEAT-1.0 | descriptive only |
| `past_integrated_cooling_energy_wh` | electrical | F1 | UNWEIGHTED | 0 | 0 | 19 | CG-FEAT-1.0 | descriptive only |
| `past_only_slope_c_per_min_60s` | rolling thermal | F1 | UNWEIGHTED | 0 | 0 | 20 | CG-FEAT-1.0 | descriptive only |

The CSV retains every feature/fold row. The top rows are shown here only to expose the synthetic pattern.

| Family | Features | Fold models | Mean share | Top feature |
|---|---:|---:|---:|---|
| door | 4 | 8 | 0.2500 | `time_since_open` |
| actuation | 3 | 8 | 0 | `time_since_confirmed_applied_change` |
| electrical | 5 | 8 | 0 | `past_integrated_cooling_energy_wh` |
| environment | 2 | 8 | 0 | `relative_humidity_pct` |
| rolling thermal | 7 | 8 | 0 | `rolling_std_temperature_60s` |
| thermal | 7 | 8 | 0 | `T_near_door_c` |

If the top feature is a door-timing or other scenario-identifying variable, that is evidence of synthetic source identification, not genuine thermal forecasting or physical causation.

Source identity:

- `dataset_id`: `W11_EXPANDED_SYNTHETIC_GROUPED`
- `fixture_version`: `coldguard-w11-synthetic-grouped-v1`
- `feature_registry_version`: `CG-FEAT-1.0`
- `feature_registry_sha256`: `1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9`
- `config_sha256`: `4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a7660dd6481ee1f71a84`
- `provenance`: `SYNTHETIC_SOFTWARE_CONTROL_ONLY`
- `locked_test_used`: `False`
- `fold_model_count`: `8`
