# W11 leakage audit

> W11 software audit. Synthetic fixtures are software controls; this document is not physical evidence and does not certify a real predictive dataset.

## Result summary

| Result | Count |
|---|---|
| `BLOCKED_BY_MISSING_EVIDENCE` | 1 |
| `NOT_APPLICABLE` | 1 |
| `PASS` | 15 |

`PASS` is only used where the named executable probe ran and passed. `NOT_TESTED` and `BLOCKED_BY_MISSING_EVIDENCE` are retained rather than upgraded.

## Risk register

| Risk | Attack mechanism | Source/API | Preventive check | Regression tests | Result | Residual limitation | Scientific consequence |
|---|---|---|---|---|---|---|---|
| LRK-01 | Rows or windows from one run land in both train and validation. | grouped_evaluation.make_grouped_folds / validate_folds | The split API accepts runs and effective groups, never rows; train and validation groups must be disjoint. | test_grouped_evaluation.py::test_folds_are_group_disjoint_and_deterministic | **PASS** | The audit cannot prove a future caller will not build a row-level dataset outside this API. | A row split would overstate AP by memorising one run's thermal history. |
| LRK-02 | Overlapping windows are generated before run partition and leak across folds. | xgb_benchmark.build_labeled_dataset / feature_rows(split=...) | Features and labels are built only for runs whose split partition is development; an unpartitioned run is refused. | test_grouped_evaluation.py::test_unpartitioned_run_is_refused | **PASS** | The benchmark trusts the supplied split identity; a forged split is outside this software control. | Window-before-split can make empty folds look separable. |
| LRK-03 | A rolling statistic uses samples after the anchor. | feature_pipeline.feature_rows | Future mutation/truncation probes must leave every past feature byte-identical. | test_w11_leakage.py::test_future_mutation_invariance | **PASS** | Covers the registered feature set only. | Future leakage would make the model clairvoyant at prediction time. |
| LRK-04 | A command, door or electrical state after t enters X_t. | feature_pipeline._compute_one | The same future mutation probe mutates all post-anchor command/state fields. | test_w11_leakage.py::test_future_mutation_invariance | **PASS** | Feature definitions are frozen only by the W10 registry identity. | A post-intervention state in X cannot be known by Controller A. |
| LRK-05 | An imputer or scaler is fitted on the union of training and validation groups. | grouped_evaluation.assert_train_only_fit | The API refuses any fit population that includes a non-training group; XGBoost's native NaN handling makes a global imputer unnecessary. | test_grouped_evaluation.py::test_fit_population_must_be_train_only | **PASS** | A caller could implement a transform outside this API. | Validation statistics would leak the validation distribution into training. |
| LRK-06 | A calibrator is fitted on the locked test partition. | xgb_benchmark.score_semantics = risk_score | No calibration is performed; outputs are labelled risk_score and calibration_status is NOT_PERFORMED. | test_xgb_benchmark.py::test_outputs_are_risk_scores_not_probabilities | **NOT_APPLICABLE** | If calibration is added later, it must be fitted on grouped development data only. | Uncalibrated scores must not be called physical probabilities. |
| LRK-07 | A decision threshold is tuned using locked-test outcomes. | grouped_evaluation.validate_run_population / risk_threshold | The operating threshold is predeclared in the config; locked-test runs are refused before prediction. | test_w11_leakage.py::test_locked_test_boundary | **PASS** | The numeric 0.5 is an illustrative development operating point, not a tuned test result. | Test-tuned thresholds overstate deployable performance. |
| LRK-08 | A renamed export or second view of one boot is counted as another run. | grouped_evaluation.validate_run_population | Each source hash and physical_source_key may belong to exactly one run and one effective group. | test_grouped_evaluation.py::test_duplicate_physical_source_is_refused; test_grouped_evaluation.py::test_pair_lineage_never_straddles_folds | **PASS** | Source identity is only as strong as the W04/W08 provenance. | Duplicate exports inflate the apparent independent population. |
| LRK-09 | A Controller B interventional trajectory is used as an observational negative. | grouped_evaluation.build_evaluation_runs | Predictive controller ids are refused for observational training. | test_grouped_evaluation.py::test_predictive_controller_is_refused | **PASS** | Controller id strings are a declared contract, not a hardware attestation. | An event prevented by intervention is an unobserved counterfactual, not a negative. |
| LRK-10 | Critical-event time, y or a post-intervention outcome is inserted into X. | xgb_benchmark.FeaturePolicy.assert_safe | The explicit allowlist must contain only frozen registry features; provenance/target fields are rejected. | test_xgb_benchmark.py::test_identifier_and_label_fields_cannot_enter_x | **PASS** | A caller could bypass the config loader and construct a custom matrix. | Label leakage yields a near-perfect but meaningless AP. |
| LRK-11 | P3 outcomes are inspected during W11 development. | grouped_evaluation.build_evaluation_runs / validate_run_population | Locked-test runs are refused by both the run builder and fold validator; the W10 test pair is untouched. | test_grouped_evaluation.py::test_locked_test_run_is_refused | **PASS** | No real P3 population exists yet; W12 owns the locked-test boundary. | Any test peek invalidates the later Gate G3 report. |
| LRK-12 | A repeated sample delivery is treated as a new independent observation. | feature_pipeline._dedupe_samples / event_evaluator.build_warning_episodes | Contradictory duplicate identities fail closed; identical duplicates are deduplicated. | test_w11_leakage.py::test_contradictory_duplicate_delivery_is_refused | **PASS** | Adapter-level dedup depends on the quality of sample identity. | Repeated deliveries can inflate sample counts and apparent warning episodes. |
| LRK-13 | Samples from separate boots are stitched onto one time axis. | feature_pipeline.Trajectory.__post_init__ | A trajectory is one device/boot acquisition domain; mixed boots are refused and must be partitioned by an adapter. | test_feature_causality.py::test_direct_constructor_refuses_mixed_boot_samples | **PASS** | Boot-scoped uptime is not absolute UTC; W11 real admission requires EVENT_UTC. | Cross-boot continuity fabricates thermal history that never existed. |
| LRK-14 | UNKNOWN electrical quality is silently filled with 0 W or 0 A. | xgb_benchmark.feature_matrix | None/absent values become NaN; the matrix never substitutes zero. | test_xgb_benchmark.py::test_missing_electrical_is_nan_not_zero | **PASS** | The model treats NaN natively; missingness semantics remain an assumption of the fixture. | Zero-filling would fabricate a measured no-load state. |
| LRK-15 | Runs from different hardware or configuration lineages are pooled. | grouped_evaluation.build_evaluation_runs | More than one hardware/config lineage in development is refused. | test_grouped_evaluation.py::test_mixed_hardware_lineage_is_refused | **PASS** | The single-rig fixture has no real multi-lineage evidence. | Pooled hardware can confound thermal behaviour with model skill. |
| LRK-16 | A model learns ambient or day-specific context that is not stable for deployment. | W11 real admission gate | No multi-day, A-valid physical population exists to probe drift. | none executed | **BLOCKED_BY_MISSING_EVIDENCE** | Needs a qualified multi-day physical dataset; synthetic fixtures cannot establish drift. | Deployment performance may degrade when ambient conditions change. |
| LRK-17 | The best-looking fold or metric is selected after seeing outcomes. | xgb_benchmark.primary_metric / imbalance.selection_rule | AP and all predeclared folds/strategies are reported; no post-hoc best-fold selection. | test_xgb_benchmark.py::test_all_folds_and_strategies_are_reported | **PASS** | A human could still selectively quote a favorable fold; the report keeps every fold visible. | Selective reporting overstates the benchmark. |

## Executable probes

| Probe | Result | Detail |
|---|---|---|
| `future_mutation` | **PASS** | future observations after 60 s mutated; 61 past anchors unchanged |
| `split_before_windows` | **PASS** | an unpartitioned run is refused before any feature window is built |
| `grouped_disjoint` | **PASS** | 4 grouped folds are disjoint and cover every development run once |
| `pair_preservation` | **PASS** | every paired S1/S2 arm stays inside one fold side |
| `locked_test` | **PASS** | locked-test runs are refused by the run builder and the fold validator |
| `predictive_intervention` | **PASS** | a Controller B interventional trajectory is refused for observational training |
| `duplicate_source` | **PASS** | two export views of one physical source are refused as independent groups |
| `duplicate_delivery` | **PASS** | a contradictory duplicate delivery fails closed in episode construction |
| `boot_boundary` | **PASS** | a mixed-boot trajectory is refused before feature computation |
| `train_only_transform` | **PASS** | a transform fitted on validation groups identifies and refuses the illegal population |
| `label_schema` | **PASS** | a future critical-event field cannot enter the feature allowlist |
| `missing_not_zero` | **PASS** | a missing/UNKNOWN electrical value becomes NaN, never a silent zero |
| `hardware_identity` | **PASS** | mixed hardware/config lineages are refused as non-comparable |
| `metric_predeclared` | **PASS** | AP and every predeclared strategy/fold are reported; no best-fold selection |
| `gate_b_bypass` | **PASS** | a forged GREEN manifest without a matching W08 receipt is refused |

## Unresolved evidence dependency

- `LRK-16` (ambient/day covariate drift) cannot be probed from the single invalid A capture or from synthetic controls. It remains `BLOCKED_BY_MISSING_EVIDENCE` until a multi-day, A-valid physical population exists.
- `LRK-06` (test-set calibration) is `NOT_APPLICABLE`: W11 is a score-only benchmark and no calibration transform is fitted.
