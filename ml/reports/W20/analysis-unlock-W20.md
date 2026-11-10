# W20 Paired-Difference Contract and Analysis Lock (B-W20-03)

Evidence class: METADATA_ONLY_FOR_REAL_CAMPAIGN plus TEST_ONLY_SOFTWARE_GATE_PROOF; no physical campaign or outcome data is present.

Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17/W18/W19 artifacts, Member A W19/W20 metadata dossiers and Member B contracts), SYNTHETIC_SOFTWARE_FIXTURE (permanently marked W20 fixture metadata), DERIVED_SOFTWARE_ASSERTION (gate, contract and causal-boundary results), EXTERNAL_DEPENDENCY (Member A/C/D and leader prerequisites), NOT_VERIFIED (absent physical campaign data and outcome payloads).

## Registered analysis identity

| Item | Registered value |
|---|---|
| Sign convention | I_i = Y_A,i - Y_B,i |
| Meaning | Positive = Controller B improved; negative = worsened |
| Independent unit | one valid matched Controller A/B pair |
| Statistical freeze fields | primary_outcome, paired_sign_convention, confidence_level, bootstrap_seed, bootstrap_iterations, test_family, invalid_pair_handling, secondary_outcomes |
| CI / test family | PRECOMPUTED_ONLY; not selected in W20 |
| Seed / iterations | FROZEN_INPUTS_REQUIRED; not computed in W20 |
| Multiplicity policy | PREDECLARED_ONLY |
| Source and result hashes | REQUIRED_AT_AUTHORIZED_EXECUTION |

## Missing freeze inputs (current evidence)

The approved statistical freeze is absent; all freeze fields remain prerequisites: primary_outcome, paired_sign_convention, confidence_level, bootstrap_seed, bootstrap_iterations, test_family, invalid_pair_handling, secondary_outcomes.

## Analysis boundary proof

```text
PAIRED_EFFECT_COMPUTED = NONE
MEAN_TREATMENT_IMPROVEMENT_COMPUTED = NONE
P_VALUE_COMPUTED = NONE
CONFIDENCE_INTERVAL_COMPUTED = NONE
SIGNIFICANCE_FLAG_PRODUCED = NONE
OUTCOME_SERIES_OPENED = NONE
ANALYSIS_ACTIONS = NONE
W20_ANALYSIS = NOT_AUTHORIZED
```

## Causal restriction (B-W20-04)

| Restriction | Enforced |
|---|---|
| CLOSED_LOOP_B_RUNS_EXCLUDED_FROM_NAIVE_EWT | true |
| UNOBSERVED_REACTIVE_CROSSING_IS_NOT_ZERO | true |
| SYNTHETIC_TIMING_NOT_PROMOTED_TO_ACTIONABILITY | true |
| ACK_NOT_SUBSTITUTED_FOR_PHYSICAL_RESPONSE | true |
| ELECTRICAL_OBSERVATION_NOT_SUBSTITUTED_FOR_THERMAL_RECOVERY | true |
| PZEM_GAP_NOT_CONVERTED_TO_ZERO_ENERGY | true |
| COOLING_BRANCH_ENERGY_NOT_WHOLE_SYSTEM_ENERGY | true |
| POST_INTERVENTION_WARNING_NOT_USED_AS_NO_CONTROL_COUNTERFACTUAL | true |

Closed-loop Controller B trajectories are physical A/B outcomes, not offline EWT evidence. An unobserved reactive crossing is not zero EWT, an ACK is not a physical response, electrical observation is not thermal recovery, a PZEM gap is not zero energy, and cooling-branch energy is not whole-system energy.

## Unlock semantics

This task produces a readiness receipt only. A separate authorized execution requires: (1) external campaign acceptance, (2) an approved statistical freeze, and (3) an approved analysis execution authorization. A software preflight success is not an authorization, and the fixture proof class is TEST_ONLY_SOFTWARE_GATE_PROOF.

Causal proof status: CAUSAL_BOUNDARY_SOFTWARE_VERIFIED.

Real gate: ANALYSIS_PREFLIGHT_BLOCKED; fixture gate: ANALYSIS_METADATA_READY_PENDING_AUTHORIZATION.
