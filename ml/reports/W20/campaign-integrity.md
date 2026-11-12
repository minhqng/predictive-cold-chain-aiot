# W20 Campaign Integrity and Analysis-Readiness Gate (B-W20-01)

Evidence class: METADATA_ONLY_FOR_REAL_CAMPAIGN plus TEST_ONLY_SOFTWARE_GATE_PROOF; no physical campaign or outcome data is present.

Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17/W18/W19 artifacts, Member A W19/W20 metadata dossiers and Member B contracts), SYNTHETIC_SOFTWARE_FIXTURE (permanently marked W20 fixture metadata), DERIVED_SOFTWARE_ASSERTION (gate, contract and causal-boundary results), EXTERNAL_DEPENDENCY (Member A/C/D and leader prerequisites), NOT_VERIFIED (absent physical campaign data and outcome payloads).

## Current campaign state

| Item | Observed |
|---|---|
| Campaign authorization | FAIL |
| Pair target | UNKNOWN_UNFROZEN |
| Counted valid pairs | 0 (NONE) |
| Analysis execution authorization | NOT_ISSUED |
| Campaign close-out | PAIR_TARGET_NOT_FROZEN |
| Gate decision | ANALYSIS_PREFLIGHT_BLOCKED |
| Proof class | METADATA_ONLY_FOR_REAL_CAMPAIGN |

## Prerequisite groups (real metadata)

### A_CAMPAIGN_AUTHORIZATION — FAIL

| Requirement | Owner | Canonical ref | Class | Status | Evidence | Blocking consequence |
|---|---|---|---|---|---|---|
| A1 | TEAM_LEAD | 03 §137; 04 W20; 05B §48 | TEAM_DEPENDENCY | FAIL | AUTHORIZATION_RECORD_MISSING | analysis preflight remains blocked |
| A5 | TEAM_LEAD | 03 §133; 04 W20 | TEAM_DEPENDENCY | FAIL | APPROVED_FREEZE_VERSION_MISSING | analysis preflight remains blocked |
| A4 | TEAM_LEAD | 03 §137 | TEAM_DEPENDENCY | FAIL | REVIEW_AUTHORITY_MISSING | analysis preflight remains blocked |
| A6 | TEAM_LEAD | 03 §137; 05D | TEAM_DEPENDENCY | FAIL | CONTROLLER_B_ENABLEMENT_MISSING | analysis preflight remains blocked |

### B_FROZEN_PAIR_TARGET — FAIL

| Requirement | Owner | Canonical ref | Class | Status | Evidence | Blocking consequence |
|---|---|---|---|---|---|---|
| B1 | TEAM_LEAD | 03 §99-101; 04 W20 | CANONICAL | FAIL | PAIR_TARGET_STATUS=UNKNOWN_UNFROZEN;PAIR_TARGET_RECORD_MISSING | analysis preflight remains blocked |

### C_VALID_PAIR_COMPLETION — FAIL

| Requirement | Owner | Canonical ref | Class | Status | Evidence | Blocking consequence |
|---|---|---|---|---|---|---|
| C1 | B | 03 §95-98; 05B §47 | CANONICAL | FAIL | PAIR_LEDGER_MISSING | analysis preflight remains blocked |

### D_HARDWARE_PROTOCOL_STABILITY — FAIL

| Requirement | Owner | Canonical ref | Class | Status | Evidence | Blocking consequence |
|---|---|---|---|---|---|---|
| D:hardware_config_id | A | 03 §34-37, §95-98 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:sensor_placement | A | 03 §34-37; 01 §1.5 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:calibration_id | A | 03 §35; 01 §18 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:firmware_version | A/C | 03 §92; 05A W20 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:model_artifact_sha256 | B | 03 §92; 05B §46 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:model_config_sha256 | B | 03 §92 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:feature_version | B | 03 §92; 05B §9 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:feature_schema_hash | B | 03 §92; 02 §60.5 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:feature_order_sha256 | B | 03 §92; 02 §60.5 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:model_calibration_semantics | B | 03 §58-60 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:primary_horizon | B/D | 03 §44, §92; 05B §41 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:critical_target | A/B | 03 §42-43 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:reactive_threshold_hysteresis | D | 03 §44, §84; 05D | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:predictive_threshold | B/D | 03 §87; 05B §43 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:warning_persistence | B/D | 03 §88; 05B §43 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:controller_policy_version | D | 02 §1.6; 04 §11.4 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:cooling_action_magnitude | D | 03 §102; 05D | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:safety_limits | D | 06; 05D | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:disturbance_protocol_id | A | 03 §34-38, §95-98 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:initial_reset_criterion | A | 03 §37 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:pair_matching_tolerances | A/B | 03 §35 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:randomization_protocol | A | 03 §36 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:analysis_plan_version | B | 03 §130-135; 05B §48 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:primary_outcome | B | 03 §68-75, §133 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |
| D:target_pair_count | TEAM_LEAD | 03 §99-101; 04 W20 | CANONICAL | FAIL | CAMPAIGN_MANIFEST_MISSING | analysis preflight remains blocked |

### E_SCIENTIFIC_FREEZE — FAIL

| Requirement | Owner | Canonical ref | Class | Status | Evidence | Blocking consequence |
|---|---|---|---|---|---|---|
| E0 | TEAM_LEAD | 03 §133; 04 W20 | CANONICAL | FAIL | CAMPAIGN_FREEZE_NOT_APPROVED;MISSING_FIELDS=hardware_config_id,calibration_id,firmware_version,sensor_placement,model_artifact_sha256,feature_schema_hash,critical_target,representative_temperature,primary_horizon,operating_threshold,warning_persistence,controller_policy_version,cooling_action_magnitude,disturbance_protocol,initial_reset_criterion,pair_matching_tolerances,randomization_protocol,validity_exclusion_rules,primary_outcome,statistical_method,target_pair_count;UNFROZEN_FIELDS=hardware_config_id,calibration_id,firmware_version,sensor_placement,model_artifact_sha256,feature_schema_hash,critical_target,representative_temperature,primary_horizon,operating_threshold,warning_persistence,controller_policy_version,cooling_action_magnitude,disturbance_protocol,initial_reset_criterion,pair_matching_tolerances,randomization_protocol,validity_exclusion_rules,primary_outcome,statistical_method,target_pair_count | analysis preflight remains blocked |
| E1 | TEAM_LEAD | 03 §130-135; 05B §48 | CANONICAL | FAIL | STATISTICAL_FREEZE_STATUS=NOT_FROZEN;STATISTICAL_FREEZE_RECORD_MISSING | analysis preflight remains blocked |
| E2 | B/TEAM_LEAD | 03 §68-75; 05B §48 | CANONICAL | FAIL | OUTCOME_DEFINITION_FREEZE_MISSING | analysis preflight remains blocked |
| E3 | B | 03 §133; 05B §48 | CANONICAL | FAIL | PRIMARY_OUTCOME_MANIFEST_IDENTITY_MISSING | analysis preflight remains blocked |

### F_EXPORT_RAW_INTEGRITY — FAIL

| Requirement | Owner | Canonical ref | Class | Status | Evidence | Blocking consequence |
|---|---|---|---|---|---|---|
| F1 | C/A | 03 §130-135; 05C W20 | TEAM_DEPENDENCY | FAIL | FINAL_EXPORT_METADATA_MISSING | analysis preflight remains blocked |
| F3 | C/A | 03 §130-135; 05C W20 | TEAM_DEPENDENCY | FAIL | FINAL_EXPORT_METADATA_MISSING | analysis preflight remains blocked |
| F4 | C/A | 03 §158-163; 05C W20 | TEAM_DEPENDENCY | FAIL | FINAL_EXPORT_METADATA_MISSING | analysis preflight remains blocked |
| F7 | C/A | 03 §130-135; 05C W20 | TEAM_DEPENDENCY | FAIL | FINAL_EXPORT_METADATA_MISSING | analysis preflight remains blocked |
| F8 | C/A | 03 §137; 05A W20 | TEAM_DEPENDENCY | FAIL | FINAL_EXPORT_METADATA_MISSING | analysis preflight remains blocked |

## Protected-identity comparability audit

| Identity | Owner | Verdict | Evidence |
|---|---|---|---|
| hardware_config_id | A | FAIL | CAMPAIGN_MANIFEST_MISSING |
| sensor_placement | A | FAIL | CAMPAIGN_MANIFEST_MISSING |
| calibration_id | A | FAIL | CAMPAIGN_MANIFEST_MISSING |
| firmware_version | A/C | FAIL | CAMPAIGN_MANIFEST_MISSING |
| model_artifact_sha256 | B | FAIL | CAMPAIGN_MANIFEST_MISSING |
| model_config_sha256 | B | FAIL | CAMPAIGN_MANIFEST_MISSING |
| feature_version | B | FAIL | CAMPAIGN_MANIFEST_MISSING |
| feature_schema_hash | B | FAIL | CAMPAIGN_MANIFEST_MISSING |
| feature_order_sha256 | B | FAIL | CAMPAIGN_MANIFEST_MISSING |
| model_calibration_semantics | B | FAIL | CAMPAIGN_MANIFEST_MISSING |
| primary_horizon | B/D | FAIL | CAMPAIGN_MANIFEST_MISSING |
| critical_target | A/B | FAIL | CAMPAIGN_MANIFEST_MISSING |
| reactive_threshold_hysteresis | D | FAIL | CAMPAIGN_MANIFEST_MISSING |
| predictive_threshold | B/D | FAIL | CAMPAIGN_MANIFEST_MISSING |
| warning_persistence | B/D | FAIL | CAMPAIGN_MANIFEST_MISSING |
| controller_policy_version | D | FAIL | CAMPAIGN_MANIFEST_MISSING |
| cooling_action_magnitude | D | FAIL | CAMPAIGN_MANIFEST_MISSING |
| safety_limits | D | FAIL | CAMPAIGN_MANIFEST_MISSING |
| disturbance_protocol_id | A | FAIL | CAMPAIGN_MANIFEST_MISSING |
| initial_reset_criterion | A | FAIL | CAMPAIGN_MANIFEST_MISSING |
| pair_matching_tolerances | A/B | FAIL | CAMPAIGN_MANIFEST_MISSING |
| randomization_protocol | A | FAIL | CAMPAIGN_MANIFEST_MISSING |
| analysis_plan_version | B | FAIL | CAMPAIGN_MANIFEST_MISSING |
| primary_outcome | B | FAIL | CAMPAIGN_MANIFEST_MISSING |
| target_pair_count | TEAM_LEAD | FAIL | CAMPAIGN_MANIFEST_MISSING |

Drift is never silently pooled. A change requires a change ID, old/new versions, reason, authoritative approver, affected attempts/pairs, a comparability decision and analysis implications; B checks metadata completeness only and never invents the approval.

## Cross-member evidence handoff

| Requirement | Owner | Source path | Revision | SHA-256 | Approval authority | Verified evidence | Verdict | Blocking consequence |
|---|---|---|---|---|---|---|---|---|
| A_W19_WAVE1 | A | evidence/A/W19/wave1-status.md | 3b27b7e | 99676d554dcce00434dd91e450979e6d5438f8097a6c6de76a333839265fe65c | Member A | Member A reports 0 completed physical runs | PENDING_OPERATOR_RUN | No physical pairs exist |
| A_W20_WAVE2 | A | evidence/A/W20/campaign-wave2-index.json | 3b27b7e | 4c58e48f3ed3d2b131eabb6f23c8177bbf02a8ac687183450f4eb93753a76d9f | Member A + operator signature | 0 runs, target_pairs 0, operator signature pending | PENDING_PHYSICAL_RUNS | Pair target and pairs absent |
| C_W20_EXPORT | C | (not present in this stack) | 659512f91c41deadef036da71544ffa8b6245d93 | ABSENT | Member C | W20 export/freeze tooling unmerged (PR 97) | UNMERGED_EXTERNAL_DEPENDENCY | No final export manifest, backup or raw-data content verification |
| D_POLICY_FREEZE | D | (not present in this stack) | da821094985006945d0306dd7b16be576378bc18 | ABSENT | Member D | No frozen final controller policy or safety envelope | NOT_FROZEN | Policy/safety comparability cannot be established |
| LEADER_AUTHORIZATION | TEAM_LEAD | ml/reports/W18/w18-manifest.json | d7bffbcfacc8505b227bd87a47dd03620ed82d16 | bd1391d72d030af5e0ca99540059424fbf45ca1ccced255e8d41ca374799c9ab | Team lead | G4 NOT_READY; Controller B signoff WITHHELD | NOT_ISSUED | Campaign, target, statistical freeze and analysis authorization remain unavailable |

## Fixture proof (software-only)

| Item | Value |
|---|---|
| Fixture gate | ANALYSIS_METADATA_READY_PENDING_AUTHORIZATION |
| Fixture close-out | CAMPAIGN_LOCK_READY_FOR_EXTERNAL_REVIEW |
| Fixture proof class | TEST_ONLY_SOFTWARE_GATE_PROOF |
| Fixture valid pairs | 1 |
| Fixture admitted to a real campaign | false |

## No-outcome-access proof

| Proof | Observed |
|---|---|
| Allowlisted metadata files read | 18 |
| Non-allowlisted path refused | true |
| Outcome-path tokens refused | thermal_series, temperature_series, power_series, energy_series, outcome |
| Static capability audit | PASS |
| A W19 checksum listing | PASS |
| A W20 checksum listing | PASS |
| Outcome analysis actions | NONE |
| Analysis code imports analysis libraries | false |

## Adversarial controls

| Control | Expectation | Passed |
|---|---|---|
| valid_fixture_reaches_metadata_ready | a permanently marked synthetic fixture passes structural groups and stops at metadata-ready pending authorization | True |
| missing_g4_blocks | missing G4 prevents analysis readiness | True |
| fake_approval_string_refused | a string containing APPROVED is not proof of authorization | True |
| development_baseline_is_not_a_freeze | the W18 development baseline never becomes a campaign freeze | True |
| target_missing_or_zero_refused | a frozen target must be a positive integer | True |
| target_reached_statistical_freeze_missing | target reached but statistical freeze missing stays blocked | True |
| target_reached_policy_freeze_missing | target reached but campaign policy freeze missing stays blocked | True |
| target_reached_backup_missing | target reached but raw export not backed up stays blocked | True |
| target_reached_physical_trace_absent | target reached but physical verification trace absent stays blocked | True |
| target_changed_after_attempts_started | an approved target cannot change after attempts started | True |
| null_freeze_value_not_approved | a freeze field with a null value cannot be approved | True |
| freeze_evidence_revision_disagrees | freeze evidence revision must match the campaign attempts | True |
| operator_override_field_refused | an operator-supplied override cannot bypass a refusal | True |
| ledger_campaign_identity_mismatch_refused | the ledger campaign identity must match the reviewed campaign metadata | True |
| ledger_frozen_target_mismatch_refused | the ledger frozen target must match the reviewed pair-target record | True |
| ledger_statistical_freeze_mismatch_refused | the ledger statistical freeze must match the reviewed freeze record | True |
| ledger_campaign_freeze_mismatch_refused | the ledger campaign freeze must match the reviewed freeze record | True |
| malformed_target_history_refused | a malformed target-history record cannot hide a post-start change | True |
| malformed_n_inflation_claim_refused | a malformed N-inflation claim cannot be treated as absent | True |
| w16_holdout_missing_refused | missing W16 holdout evidence fails closed | True |
| w16_holdout_malformed_refused | malformed W16 holdout evidence fails closed | True |
| valid_pair_counted_once | one valid pair contributes exactly one observation | True |
| same_run_id_across_attempts_refused | the same run counted twice is refused | True |
| same_physical_source_refused | one physical source cannot appear under different run ids | True |
| rerun_of_valid_arm_refused | rerunning a valid arm is not an opportunity to improve results | True |
| invalidate_pair_rule_not_bypassed | an INVALIDATE_PAIR rule cannot be bypassed by a rerun | True |
| invalid_attempt_omitted_refused | an invalid attempt cannot be omitted from history | True |
| aborted_attempt_dropped_refused | an aborted attempt cannot be dropped from the final ledger | True |
| missing_second_arm_not_valid | a missing second arm cannot count as a valid pair | True |
| superseded_attempt_not_independent_pair | a superseded attempt cannot become an independent pair | True |
| target_reached_only_by_duplicates_refused | a target reached only through duplicated attempts is refused | True |
| incomplete_quality_not_valid | incomplete data quality cannot be treated as valid | True |
| incorrect_controller_order_refused | an incorrect controller order cannot be accepted silently | True |
| model_artifact_changed | version/protocol drift is detected at D_HARDWARE_PROTOCOL_STABILITY | True |
| feature_schema_changed | version/protocol drift is detected at D_HARDWARE_PROTOCOL_STABILITY | True |
| policy_threshold_changed | version/protocol drift is detected at D_HARDWARE_PROTOCOL_STABILITY | True |
| warning_persistence_changed | version/protocol drift is detected at D_HARDWARE_PROTOCOL_STABILITY | True |
| cooling_magnitude_changed | version/protocol drift is detected at D_HARDWARE_PROTOCOL_STABILITY | True |
| hardware_or_firmware_changed | version/protocol drift is detected at D_HARDWARE_PROTOCOL_STABILITY | True |
| calibration_changed | version/protocol drift is detected at D_HARDWARE_PROTOCOL_STABILITY | True |
| disturbance_protocol_changed | version/protocol drift is detected at D_HARDWARE_PROTOCOL_STABILITY | True |
| initial_tolerance_changed | version/protocol drift is detected at D_HARDWARE_PROTOCOL_STABILITY | True |
| primary_outcome_definition_changed | version/protocol drift is detected at E_SCIENTIFIC_FREEZE | True |
| drift_without_comparability_approval | version/protocol drift is detected at D_HARDWARE_PROTOCOL_STABILITY | True |
| thermal_outcome_payload_refused | the preflight cannot open a thermal outcome payload | True |
| power_outcome_payload_refused | the preflight cannot open a power outcome series | True |
| p_value_capability_refused | a p-value computation is statically rejected | True |
| paired_effect_capability_refused | a paired-effect vector or CI cannot be produced | True |
| effect_based_pair_selection_refused | invalid pairs cannot be removed based on effect direction | True |
| synthetic_outcome_table_refused | a pair-outcomes.csv cannot be generated from a synthetic fixture | True |
| locked_test_opened_refused | an opened W16 locked test blocks the campaign lock | True |
| preflight_does_not_start_analysis | a successful software preflight never starts the final analysis | True |
| cli_override_refused | an unapproved CLI override cannot trigger evaluation | True |
| report_keeps_analysis_not_run | no result report claims scientific acceptance while analysis is NOT_RUN | True |
| closed_loop_b_ewt_refused | a B-controlled trajectory cannot supply a naive counterfactual EWT | True |
| missing_ewt_not_zero | an unobserved reactive crossing is not an EWT of zero | True |
| missing_aiw_not_zero | missing AIW latency inputs are not zero | True |
| ack_not_physical_response | an ACK is not a physical response | True |
| electrical_not_thermal_recovery | electrical observation cannot substitute for verified thermal recovery | True |
| pzem_gap_not_zero_energy | a PZEM gap is not interpreted as zero energy | True |
| cooling_branch_not_whole_system | cooling-branch energy is not whole-system energy | True |
| unfrozen_representative_temperature_refused | an unfrozen representative temperature blocks the outcome definition | True |
| synthetic_timing_not_actionability | synthetic timing cannot be promoted to real actionability evidence | True |
| post_intervention_warning_not_counterfactual | post-intervention warning timing is not a no-control counterfactual | True |
| unknown_provenance_aiw_refused | AIW metadata with unknown provenance fails closed | True |

Controls passed: 65/65

## Unfinished scientific work

The final physical A/B campaign, accepted pair ledger, pair target, hardware/protocol freeze, statistical freeze, outcome-definition freeze, final export/backup and physical verification trace are all absent. Therefore B-W20-02 actual outcomes and B-W20-03 actual paired differences remain NOT_COMPUTED, G5 remains NOT_ESTABLISHED, and the W16 locked test remains unopened.

## One next Member B action

Keep W20 final analysis locked; when Member A and Member C publish the accepted final campaign export and the leader issues the campaign and statistical freezes, re-run the W20 preflight against that metadata and request external review. Do not open physical outcomes, compute paired effects or start W21 implementation in this task.

## Verdict

```text
CAMPAIGN_LOCK = BLOCKED
FINAL_CAMPAIGN = NOT_AUTHORIZED
PAIR_TARGET = UNKNOWN_UNFROZEN
W20_ANALYSIS = NOT_AUTHORIZED
G4 = NOT_READY
G5 = NOT_ESTABLISHED
```
