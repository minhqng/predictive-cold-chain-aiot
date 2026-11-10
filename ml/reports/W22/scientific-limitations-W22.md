# B-W22-06 — Scientific limitations and final-report contract

> **TEMPLATE ONLY — NO RESULT. TEST_ONLY harness; no physical data.** The
> physical analysis has not run.

## Current scientific status

| field | value |
|---|---|
| real accepted pair count | NOT_ESTABLISHED (no campaign completed) |
| pair target | UNKNOWN_UNFROZEN |
| statistical freeze | NOT_FROZEN |
| analysis authorization | NOT_AUTHORIZED |
| physical inference | NOT_COMPUTED |
| W16 holdout | NOT_OPENED |
| G4 | NOT_READY |
| G5 | NOT_ESTABLISHED |
| W20 final analysis | LOCKED |

## Separate scientific questions

- **Predictive quality:** did the model identify an impending thermal
  event on eligible non-intervened data?
- **Physical treatment effect:** did Controller B actually improve the
  measured thermal or energy outcome relative to Controller A?

These questions have different evidence requirements. Synthetic AP,
synthetic A1/A2/A3 gains, offline EWT, model serialization checks and
diagnosis software tests are not substitutes for a real physical paired
A/B result.

## Final report template

# Final matched Controller A/B report — template

> TEMPLATE ONLY — NO RESULT. The final physical analysis has not run.

## Scientific questions (separate evidence requirements)

- Predictive quality: Did the model identify an impending thermal event on eligible non-intervened data?
- Physical treatment effect: Did Controller B actually improve the measured thermal or energy outcome relative to Controller A?

## Required sections

1. population and pair flow with exclusion reasons
2. excluded/invalid pair table with rule citations
3. method statement: primary CI, bootstrap seed/iterations, test family
4. descriptive statistics with raw arms and I_i per pair
5. primary 95% CI and physically interpreted effect size
6. predeclared test result with assumption license
7. sensitivity and exploratory section, each labelled
8. scientific limitations
9. provenance: dataset/split/manifest ids, seeds, code version, freeze gates

## Mandatory limitations

- Independent pair count: the inferential unit is one accepted matched Controller A/B pair; telemetry rows, windows and repeated event samples add no independent N.
- Invalid or excluded pairs: every exclusion is listed with its rule, and a valid extreme pair is never removed from the primary analysis.
- Dependence between runs on one rig: repeated runs share session context and are not multi-site evidence.
- One chamber and one hardware unit: the campaign is a single apparatus, not a population of installations.
- Scenario-specific model: predictive quality is conditional on the frozen scenario, features, threshold and policy.
- Potential run-order and ambient drift: randomization, reset criteria and recorded order bound the bias but do not eliminate it.
- Physical measurement and calibration limitations: sensor placement, ROM identity, calibration lineage and timing provenance constrain what the outcome numbers mean.
- PZEM cooling-branch-only energy: energy is measured on the cooling branch, never whole-system energy.
- Small-N confidence-interval sensitivity: interval width and method choice matter more as N shrinks; a zero-width interval is not proof of certainty.
- Uncertainty from incomplete recovery: censored recovery is never a finite time and never enters as a numeric outcome.
- Missing physical model acceptance: software verification, synthetic metrics and offline replay are not a physical model acceptance.
- No biological quality ground truth: product-quality claims are outside the measured thermal/energy outcomes.
- Inability to infer unobserved counterfactual outcomes: the closed-loop A/B pair identifies a measured difference under the frozen protocol, not every counterfactual trajectory.

## Interpretation categories

Current: `NO_INTERPRETATION_ANALYSIS_NOT_RUN`.

- `SUPPORTS_PHYSICAL_BENEFIT`
- `MIXED_OR_UNCERTAIN_EVIDENCE`
- `DOES_NOT_SUPPORT_PHYSICAL_BENEFIT`
- `NO_INTERPRETATION_ANALYSIS_NOT_RUN`

## EWT causal boundary

CLOSED_LOOP_PHYSICAL_AB_OUTCOME cannot provide a naive counterfactual EWT; the reactive crossing that predictive action prevented is not observable and must not be invented.

## Synthetic evidence is not physical evidence

Synthetic AP, synthetic A1/A2/A3 gains, offline EWT, model serialization checks and diagnosis software tests are not a physical paired A/B result.

## Withheld while the analysis remains locked

- every-pair physical result plot
- final paired statistics over accepted physical pairs
- primary 95% confidence interval
- predeclared paired test result
- physical effect size
- real sensitivity analysis
- final scientific-limitations statement for the campaign


## Analysis status

`NO_INTERPRETATION_ANALYSIS_NOT_RUN` is the only
permitted real-result category in the current repository state.

## Withheld physical artifacts

- every-pair physical result plot
- final paired statistics over accepted physical pairs
- primary 95% confidence interval
- predeclared paired test result
- physical effect size
- real sensitivity analysis
- final scientific-limitations statement for the campaign

## Mandatory limitations

1. Independent pair count: the inferential unit is one accepted matched Controller A/B pair; telemetry rows, windows and repeated event samples add no independent N.
2. Invalid or excluded pairs: every exclusion is listed with its rule, and a valid extreme pair is never removed from the primary analysis.
3. Dependence between runs on one rig: repeated runs share session context and are not multi-site evidence.
4. One chamber and one hardware unit: the campaign is a single apparatus, not a population of installations.
5. Scenario-specific model: predictive quality is conditional on the frozen scenario, features, threshold and policy.
6. Potential run-order and ambient drift: randomization, reset criteria and recorded order bound the bias but do not eliminate it.
7. Physical measurement and calibration limitations: sensor placement, ROM identity, calibration lineage and timing provenance constrain what the outcome numbers mean.
8. PZEM cooling-branch-only energy: energy is measured on the cooling branch, never whole-system energy.
9. Small-N confidence-interval sensitivity: interval width and method choice matter more as N shrinks; a zero-width interval is not proof of certainty.
10. Uncertainty from incomplete recovery: censored recovery is never a finite time and never enters as a numeric outcome.
11. Missing physical model acceptance: software verification, synthetic metrics and offline replay are not a physical model acceptance.
12. No biological quality ground truth: product-quality claims are outside the measured thermal/energy outcomes.
13. Inability to infer unobserved counterfactual outcomes: the closed-loop A/B pair identifies a measured difference under the frozen protocol, not every counterfactual trajectory.
