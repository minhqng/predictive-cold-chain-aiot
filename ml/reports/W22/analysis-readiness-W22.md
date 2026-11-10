# W22 analysis-readiness and W20 gate binding

> **TEST_ONLY HARNESS — NO REAL ANALYSIS.** No physical paired analysis
> is authorized or executed by W22.

## Authoritative gate

The W20 campaign-lock assessment remains the only admission authority.
W22's readiness function accepts campaign metadata (never a pre-labelled
assessment object) and calls `assess_campaign_lock` itself. It refuses
real analysis unless the gate decision is
`ANALYSIS_AUTHORIZED_FOR_SEPARATE_EXECUTION`, the analysis
authorization status is `ISSUED`, no refusal reasons remain, and the
assessment reports no outcome access. W22 introduces no second path.

## Toy metadata-only gate proof

| probe | gate decision | analysis authorization | readiness | outcome access |
|---|---|---|---|---|
| blocked toy bundle | ANALYSIS_PREFLIGHT_BLOCKED | NOT_ISSUED | NOT_AUTHORIZED | false |
| toy bundle with fake embedded approval | ANALYSIS_PREFLIGHT_BLOCKED | ISSUED | NOT_AUTHORIZED | false |

A fake embedded approval is rejected: the authorization must be
externally verified and file-bound, and the remaining campaign groups
still block the gate.

## Current observed status (from W20/W21 metadata manifests)

| field | value | source |
|---|---|---|
| FINAL_AB_CAMPAIGN | NOT_AUTHORIZED | W20 manifest |
| PAIR_TARGET | UNKNOWN_UNFROZEN | W20 manifest |
| W20_ANALYSIS | NOT_AUTHORIZED | W20 manifest |
| W16_HOLDOUT | NOT_OPENED | W20 manifest |
| W20_FINAL_ANALYSIS | LOCKED | W21 manifest |
| G4 | NOT_READY | W21 manifest |
| G5 | NOT_ESTABLISHED | W21 manifest |
| W13 primary horizon | UNFROZEN | W21 manifest |
| W15 model | SYNTHETIC_NONDEPLOYABLE | W21 manifest |

## Necessary conditions for a future real analysis

1. Gate G4 ready and final A/B campaign authorized
2. frozen pair target completed
3. completed accepted matched pairs with full attempt history
4. approved hardware/model/policy freeze
5. approved statistical and outcome-definition freeze
6. accepted physical-source and export hashes
7. verified backup/trace provenance
8. externally verified analysis-execution authorization (W20 gate decision)
9. separately reviewed real-data intake bridge (not implemented in W22)

## Why the pure engine cannot reach real campaign data

- the pure modules accept only in-memory numeric pairs and import no
  file, CSV, telemetry, database or broker module;
- the W22 driver has no input-file option and cannot read a
  `pair-outcomes.csv`;
- the engine is not imported by the W20 preflight or W19 gates, and
  those modules were not modified;
- W19's no-peeking behaviour and W20's outcome-access lock remain
  intact, and W16 locked-test files are untouched;
- even an authorized W20 decision would only permit a separately
  reviewed intake bridge, which W22 does not implement.

## Verdicts

```text
PHYSICAL_ANALYSIS = NOT_AUTHORIZED
REAL_PAIRED_STATISTICS = NOT_COMPUTED
FINAL_PHYSICAL_CI = NOT_COMPUTED
FINAL_PHYSICAL_P_VALUE = NOT_COMPUTED
FINAL_PHYSICAL_EFFECT = NOT_ESTABLISHED
W20_ANALYSIS_GATE = LOCKED
G4 = NOT_READY
G5 = NOT_ESTABLISHED
```
