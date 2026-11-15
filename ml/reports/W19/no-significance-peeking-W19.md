# W19 No-Significance-Peeking Verification (B-W19-03)

Evidence class: SYNTHETIC_SOFTWARE_CONTROL_ONLY (software verification; no physical campaign data).

Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17/W18 artifacts and Member B contracts), SYNTHETIC_SOFTWARE_FIXTURE (permanently marked W19 fixture ledger), DERIVED_SOFTWARE_ASSERTION (ledger/validity/progress results), EXTERNAL_DEPENDENCY (A/C/D and leader prerequisites), NOT_VERIFIED (absent physical campaign data).

## Permitted and prohibited W19 computations

| Allowed in W19 | Prohibited in W19 |
|---|---|
| `attempt_identity_validation` | `best_worst_outcome_selection` |
| `campaign_progress` | `confidence_interval_final_effect` |
| `data_quality_status` | `final_physical_effectiveness_verdict` |
| `pair_eligibility` | `headline_p_value` |
| `protocol_violations` | `interim_model_policy_optimization` |
| `provenance_integrity_checks` | `mean_controller_b_benefit` |
| `run_completeness` | `pairwise_improvement_distribution` |
| `safety_record_inspection` | `significance_based_early_stopping` |

The prohibition is structural: no W19 source implements an outcome analysis, prohibited operations are refused at runtime, and the static audit rejects forbidden imports, calls and definitions.

## Campaign stop reasons

| Permitted operational stop | Rule |
|---|---|
| `SAFETY_RESTRICTION` | documented safety restriction |
| `EQUIPMENT_FAILURE` | equipment failure |
| `FEASIBILITY_RESTRICTION` | genuine feasibility restriction |
| `AUTHORIZED_OPERATIONAL_CHANGE` | authorized operational change |

A statistically favorable interim result is not a permitted stop reason. A safety stop is recorded as operational evidence, never as a win.

## Static capability audit

Files scanned: 10; findings: 0; passed: True.

## W16 isolation

W16 locked holdout status: `NOT_OPENED` (frozen=False, opened_at=None, test_partition_used=False). A W19 ledger never releases the W16 restriction.

## Runtime controls

| Control | Expectation | Passed |
|---|---|---|
| static_source_capability_audit | no W19 source imports or calls an outcome-analysis capability | True |
| prohibited_operation_refused | a prohibited computation identifier is refused at runtime | True |
| unknown_operation_refused | the guard fails closed for unknown operations | True |
| allowed_operation_is_outcome_blind | allowed operations carry no outcome access | True |
| outcome_payload_refused_globally | an outcome-shaped payload is refused before use | True |
| statistical_stop_reason_refused | a favorable interim result is not a permitted stop reason | True |
| safety_stop_is_operational | a safety stop is operational evidence, never a statistical win | True |
| w16_holdout_isolated | the W16 locked holdout is not opened by W19 | True |

```text
NO_PEEKING = SOFTWARE_VERIFIED
P_VALUE_COMPUTED = NONE
CONFIDENCE_INTERVAL_COMPUTED = NONE
PAIRED_EFFECT_COMPUTED = NONE
W16_HOLDOUT = NOT_OPENED
```

No approval, signature, date or signoff record is fabricated by this report.
