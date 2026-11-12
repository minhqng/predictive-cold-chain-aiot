# W18 model runtime monitoring — software scope

Evidence class: SYNTHETIC_SOFTWARE_CONTROL_ONLY.
Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17 and Member A files), SYNTHETIC_SOFTWARE_FIXTURE (W17 replay and TEST_ONLY fixture), DERIVED_SOFTWARE_ASSERTION (monitor/trace/freeze/readiness results), EXTERNAL_DEPENDENCY (A/C/D interface snapshots), NOT_VERIFIED (absent live/physical evidence).
The monitor is read-only: it inspects declared prediction records and never
deploys, registers, dispatches, tunes or physically authorizes anything.

## Expected identity (computed from actual W15/W10 files)

| field | value | canonical ref |
|---|---|---|
| artifact_id | coldguard-w15-synthetic-xgb-candidate-v1 | 05B §46 |
| model_artifact_sha256 | 25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f | 03 §92 |
| model_config_sha256 | 4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a7660dd6481ee1f71a84 | 03 §92 |
| model_library_version | 3.4.1 | 03 §92 |
| feature_version | CG-FEAT-1.0 | 05B §9 |
| feature_schema_sha256 | 1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9 | 03 §92 |
| ordered_feature_ids_sha256 | 98491993d95ba78292cc245d637a1832ebdfb80b1eb026361e39926fb331223c | 02 §60.5 |
| feature_count | 28 | 05B §46 |
| score_semantics | risk_score | 03 §58-60 |
| target_status | DEVELOPMENT_CANDIDATE_NOT_FROZEN | 03 §42-43 |
| horizon | 60 s / ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN | 03 §44 |
| operating_threshold | 0.5 / ILLUSTRATIVE_NOT_FROZEN | 03 §87 |
| warning_persistence_status | NOT_FROZEN | 03 §88 |
| calibration_status | RISK_SCORE_ONLY | 03 §58-60 |
| data_evidence_class | SYNTHETIC_SOFTWARE_CONTROL_ONLY | 03 §3 |
| release_eligibility | NON_DEPLOYABLE_CANDIDATE | 05B §44 |

## Records monitored

W17 replay records inspected: 783.
W15 model manifest SHA-256: 85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e.

Verdict counts:

| verdict | count |
|---|---|
| MONITOR_SOFTWARE_VALID | 783 |

Refusal reason counts:

None.

## Identity is not approval

| question | value |
|---|---|
| MODEL_HASH_MATCH | true |
| FEATURE_SCHEMA_MATCH | true |
| OFFLINE_REPLAY_SCORE_VALID | true |
| MODEL_RELEASE_APPROVED | false |
| PHYSICAL_CONTROLLER_B_AUTHORIZED | false |
| RELEASE_CLAIM_COUNT | 0 |
| CONTROL_CLAIM_COUNT | 0 |

## Boot/sequence continuity

Groups: 16; issues: none.

| run_id | boot_id | records | first_seq | last_seq | monotonic |
|---|---|---|---|---|---|
| CG-W11-S1-003 | CG-W11-S1-003-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S1-004 | CG-W11-S1-004-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S1-005 | CG-W11-S1-005-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S1-006 | CG-W11-S1-006-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S1-007 | CG-W11-S1-007-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S1-008 | CG-W11-S1-008-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S1-009 | CG-W11-S1-009-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S1-010 | CG-W11-S1-010-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S2-003 | CG-W11-S2-003-BOOT-1 | 48 | 0 | 180 | True |
| CG-W11-S2-004 | CG-W11-S2-004-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S2-005 | CG-W11-S2-005-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S2-006 | CG-W11-S2-006-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S2-007 | CG-W11-S2-007-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S2-008 | CG-W11-S2-008-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S2-009 | CG-W11-S2-009-BOOT-1 | 49 | 0 | 180 | True |
| CG-W11-S2-010 | CG-W11-S2-010-BOOT-1 | 49 | 0 | 180 | True |

## Representative record — dimension status

| dimension | checks | pass | fail | not_verified |
|---|---|---|---|---|
| MODEL_IDENTITY | 7 | 7 | 0 | 0 |
| FEATURE_IDENTITY | 6 | 6 | 0 | 0 |
| PREDICTION_SEMANTICS | 4 | 4 | 0 | 0 |
| FRESHNESS | 6 | 6 | 0 | 0 |

## Negative controls

These probes mutate an in-memory copy of one accepted record; no committed
artifact is modified.

| probe | expected | observed | passed |
|---|---|---|---|
| wrong_model_sha | REFUSED_MODEL_IDENTITY | REFUSED_MODEL_IDENTITY | True |
| wrong_config_binding | REFUSED_MODEL_IDENTITY | REFUSED_MODEL_IDENTITY | True |
| wrong_library_version | REFUSED_MODEL_IDENTITY | REFUSED_MODEL_IDENTITY | True |
| missing_model_identity | REFUSED_MODEL_IDENTITY | REFUSED_MODEL_IDENTITY | True |
| wrong_ordered_feature_hash | REFUSED_FEATURE_IDENTITY | REFUSED_FEATURE_IDENTITY | True |
| feature_vector_tamper | REFUSED_FEATURE_IDENTITY | REFUSED_FEATURE_IDENTITY | True |
| missing_value_zero_filled | REFUSED_FEATURE_IDENTITY | REFUSED_FEATURE_IDENTITY | True |
| release_authorization_claim | REFUSED_RELEASE_AUTHORIZATION | REFUSED_RELEASE_AUTHORIZATION | True |
| release_eligibility_claim | REFUSED_RELEASE_AUTHORIZATION | REFUSED_RELEASE_AUTHORIZATION | True |
| physical_evidence_class_claim | REFUSED_EVIDENCE_CLASS | REFUSED_EVIDENCE_CLASS | True |
| threshold_claimed_frozen | REFUSED_POLICY_UNFROZEN | REFUSED_POLICY_UNFROZEN | True |
| dispatchable_policy_claim | REFUSED_RELEASE_AUTHORIZATION | REFUSED_RELEASE_AUTHORIZATION | True |
| stale_input_with_score | REFUSED_STALE_INPUT | REFUSED_STALE_INPUT | True |
| fresh_input_without_score | REFUSED_PREDICTION_SEMANTICS | REFUSED_PREDICTION_SEMANTICS | True |
| future_observation_in_prediction | REFUSED_TEMPORAL_ORDER | REFUSED_TEMPORAL_ORDER | True |
| missing_event_time_provenance | REFUSED_TEMPORAL_ORDER | REFUSED_TEMPORAL_ORDER | True |

## Limitations

- W17 replay records are synthetic software controls, not live inference.
- W17 records do not declare a model-config hash; config binding is verified
  through the W15 manifest and the actual config file.
- The runtime freshness policy remains pending C/D.
- A hash match proves byte identity only; it does not approve release.
