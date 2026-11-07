# W10 S2 causal feature report

> Software pipeline report. Synthetic results are software controls, never physical evidence. The real A capture is diagnostic only: Gate B is RED and no eligible S2 disturbance exists.

## 1. Scientific status

| Domain | Status |
|---|---|
| W10 software | GREEN |
| Independent review | RECORDED_IN_STACKED_PR |
| Physical Gate B | RED |
| Eligible real S2 data | NOT_AVAILABLE |
| Real label pilot | NOT_EVALUABLE |
| Feature causality | VERIFIED_BY_TESTS |
| Real predictive benchmark | NOT_ESTABLISHED |

## 2. Frozen feature registry identity

- Feature schema version: `CG-FEAT-1.0`
- Registry SHA-256: `ddbfe96e530d2dda79246dbb8eadd800922ea3aa03dbf4aacde433736b38136b`
- Feature count: 31
- Freeze status: `FROZEN_DEFINITIONS`
- Frozen scope: feature_names, formulas, source_roles, input_quality_requirements, lookback_semantics, missingness_behavior, feature_order, feature_schema_hash
- Not frozen here: T_critical_c, representative_temperature_for_final_labels, primary_horizon_H, operating_threshold, warning_persistence, matching_tolerances, physical_completeness_thresholds

| Family | Features |
|---|---|
| `instantaneous_thermal` | `T_chamber_max_c`, `T_chamber_min_c`, `T_chamber_mean_c`, `T_chamber_spread_c`, `T_center_c`, `T_bottom_c`, `T_near_door_c` |
| `diagnostic_thermal` | `T_tec_hot_side_c` |
| `rolling_thermal` | `rolling_mean_temperature_60s`, `rolling_std_temperature_60s`, `rolling_min_temperature_60s`, `rolling_max_temperature_60s`, `past_only_slope_c_per_min_60s`, `past_only_temperature_delta_60s`, `past_only_spatial_spread_60s` |
| `door_context` | `door_open`, `time_since_open`, `duration_so_far`, `count_past_60s` |
| `actuation_context` | `requested_cooling`, `applied_cooling`, `readback_cooling`, `applied_duty`, `time_since_confirmed_applied_change` |
| `electrical_context` | `cooling_voltage_v`, `cooling_current_a`, `cooling_power_w`, `energy_counter_wh`, `past_integrated_cooling_energy_wh` |
| `environmental_context` | `ambient_temperature_c`, `relative_humidity_pct` |

Role policy: `CHAMBER_CENTER`, `CHAMBER_BOTTOM` and `CHAMBER_NEAR_DOOR` form the chamber-air aggregate; `TEC_HOT_SIDE` is a separate diagnostic feature and is never averaged into chamber air.

## 3. Pipeline and split discipline

- Synthetic fixture version: `coldguard-w10-synthetic-s2-v1`
- Paired grouped split seed: 7 (groups: 3)
- Train runs: CG-S1-A-003, CG-S2-A-003
- Validation runs: CG-S1-A-001, CG-S2-A-001
- Test runs (untouched by W10): CG-S1-A-002, CG-S2-A-002
- Pair lineage: paired S1/S2 runs share one partition; no row-level split.
- Rolling features use the `(t - lookback, t]` convention on actual event time; no future sample, no sample-count padding, no cross-boot continuity.

## 4. Software-only synthetic S2 controls

- Development trajectories analysed: 4
- Door openings (trusted transitions): 2
- Feature anchors: 484
- Feature values present: 12746 of 15004
- Candidate horizons: [30.0, 60.0, 120.0, 300.0]
- Future-perturbation invariance: PASS
- Future-truncation invariance: PASS
- Deterministic recompute: PASS

Synthetic label-pilot counts (development partitions only):

| H (s) | Runs | Anchors | Positive | Negative | Censored | Untrusted | Prevalence |
|---|---|---|---|---|---|---|---|
| 30 | 4 | 484 | 60 | 304 | 120 | 0 | 0.1648 |
| 60 | 4 | 484 | 120 | 162 | 202 | 0 | 0.4255 |
| 120 | 4 | 484 | 160 | 2 | 322 | 0 | 0.9877 |
| 300 | 4 | 484 | 160 | 0 | 324 | 0 | 1.0000 |

A single-class population is not evidence that supervised evaluation is ready. No model was trained and no AP benchmark was computed.

## 5. Real A W09 diagnostic feature view

- Source: `../evidence/A/W09/exports/CG-S1-H8C-600S.json`
- Source SHA-256: `f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb`
- Rows: 957
- Boot id: `56044b74`
- Run identity: UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID
- Time domain: `BOOT_SCOPED_UPTIME` (absolute device UTC not evidenced)
- W08 Gate B: `RED`; A ledger: `INVALID`
- Eligible S1 runs: 0; eligible S2 runs: 0
- Door openings observed: 0
- Diagnostic feature rows: 957
- Diagnostic feature values present: 18477
- Eligible real S2 feature rows: 0
- Real label pilot: `NOT_EVALUABLE`

The real capture carries boot-scoped uptime, no verified absolute UTC, unresolved run identity, electrical quality UNKNOWN and an unconfirmed door polarity. Door and electrical features stay missing; no S2 door opening is inferred. T2 hot side is plotted separately and excluded from chamber air.

## 6. First-valid-timestamp audit (synthetic development)

| Feature | First eligible anchor (s) | First value anchor (s) | Missing reasons |
|---|---|---|---|
| `T_chamber_max_c` | 0.0 | 0.0 | none |
| `T_chamber_min_c` | 0.0 | 0.0 | none |
| `T_chamber_mean_c` | 0.0 | 0.0 | none |
| `T_chamber_spread_c` | 0.0 | 0.0 | none |
| `T_center_c` | 0.0 | 0.0 | none |
| `T_bottom_c` | 0.0 | 0.0 | none |
| `T_near_door_c` | 0.0 | 0.0 | none |
| `T_tec_hot_side_c` | 0.0 | 0.0 | none |
| `rolling_mean_temperature_60s` | 60.0 | 60.0 | `MISSING_INSUFFICIENT_HISTORY`=240 |
| `rolling_std_temperature_60s` | 60.0 | 60.0 | `MISSING_INSUFFICIENT_HISTORY`=240 |
| `rolling_min_temperature_60s` | 60.0 | 60.0 | `MISSING_INSUFFICIENT_HISTORY`=240 |
| `rolling_max_temperature_60s` | 60.0 | 60.0 | `MISSING_INSUFFICIENT_HISTORY`=240 |
| `past_only_slope_c_per_min_60s` | 60.0 | 60.0 | `MISSING_INSUFFICIENT_HISTORY`=240 |
| `past_only_temperature_delta_60s` | 60.0 | 60.0 | `MISSING_INSUFFICIENT_HISTORY`=240 |
| `past_only_spatial_spread_60s` | 60.0 | 60.0 | `MISSING_INSUFFICIENT_HISTORY`=240 |
| `door_open` | 0.0 | 0.0 | `MISSING_UNKNOWN_DOOR`=6 |
| `time_since_open` | 0.0 | 40.0 | `MISSING_NO_OBSERVED_TRANSITION`=322 |
| `duration_so_far` | 0.0 | 0.0 | `MISSING_UNKNOWN_DOOR`=6 |
| `count_past_60s` | 0.0 | 0.0 | none |
| `requested_cooling` | 0.0 | 0.0 | none |
| `applied_cooling` | 0.0 | 0.0 | none |
| `readback_cooling` | 0.0 | 0.0 | none |
| `applied_duty` | 0.0 | 30.0 | `MISSING_INPUT`=120 |
| `time_since_confirmed_applied_change` | 0.0 | 30.0 | `MISSING_INPUT`=120 |
| `cooling_voltage_v` | 0.0 | 0.0 | none |
| `cooling_current_a` | 0.0 | 0.0 | none |
| `cooling_power_w` | 0.0 | 0.0 | none |
| `energy_counter_wh` | 0.0 | 0.0 | none |
| `past_integrated_cooling_energy_wh` | 1.0 | 1.0 | `MISSING_INSUFFICIENT_HISTORY`=4 |
| `ambient_temperature_c` | 0.0 | 0.0 | none |
| `relative_humidity_pct` | 0.0 | 0.0 | none |

## 7. Artifacts

```text
ml/feature-registry-v1.yaml
ml/src/coldguard_ml/feature_registry.py
ml/src/coldguard_ml/feature_pipeline.py
ml/src/coldguard_ml/feature_fixtures.py
ml/src/coldguard_ml/feature_plot.py
ml/src/coldguard_ml/label_pilot.py
ml/scripts/feature-pipeline-W10.py
ml/tests/test_feature_registry.py
ml/tests/test_feature_causality.py
ml/tests/test_feature_pipeline.py
ml/reports/W10/S2-feature-report.md
ml/reports/W10/feature-audit-W10.svg
ml/reports/W10/real-diagnostic-W10.svg
ml/reports/W10/feature-summary-W10.csv
ml/reports/W10/label-pilot-W10.csv
ml/reports/W10/feature-manifest-W10.json
```

## 8. Boundaries

- No model training, no AP benchmark, no W11/W12 work.
- No merge, no locked-test access, no physical operation.
- No physical threshold, representative temperature or primary horizon is frozen by this report.

Audit trajectory: `CG-S2-A-003` (software-only synthetic control).
