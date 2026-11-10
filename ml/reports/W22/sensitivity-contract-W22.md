# B-W22-05 — Sensitivity and robustness contract

> **SOFTWARE CONTRACT + TOY VERIFICATION ONLY.** Sensitivity discloses
> dependence on analytical choices; it is not a route to selecting a
> favourable result. The primary analysis always retains all valid pairs.

## Rules

- The primary statistic is predeclared; every alternative is labelled
  `SENSITIVITY_ONLY_NOT_PRIMARY` and cannot be promoted.
- A leave-one-pair-out run reports the omitted pair, the changed N and
  the difference from the primary; it never invalidates the pair and
  never changes the primary result.
- A valid extreme pair cannot be excluded from the primary merely because
  it changes significance.
- A PREDECLARED sensitivity requires a frozen plan reference; otherwise
  it is EXPLORATORY.
- Secondary outcomes stay secondary; no post-result promotion.
- Alternate prediction horizons are not implemented in W22 because the
  W13 primary horizon remains unfrozen.

## Leave-one-pair-out (TEST_ONLY, EXPLORATORY)

| sensitivity ID | status | omitted pair | input pairs | valid N | mean without pair | delta from primary | label | interpretation boundary |
|---|---|---|---|---:|---:|---:|---|---|
| SENS-LOO-P-01 | EXPLORATORY | P-01 | all admitted minus P-01 | 7 | 6.71428571429 | -1.66071428571 | `SENSITIVITY_ONLY_NOT_PRIMARY` | primary retains every valid pair; omission is not invalidation |
| SENS-LOO-P-02 | EXPLORATORY | P-02 | all admitted minus P-02 | 7 | 8.85714285714 | 0.482142857143 | `SENSITIVITY_ONLY_NOT_PRIMARY` | primary retains every valid pair; omission is not invalidation |
| SENS-LOO-P-03 | EXPLORATORY | P-03 | all admitted minus P-03 | 7 | 8.85714285714 | 0.482142857143 | `SENSITIVITY_ONLY_NOT_PRIMARY` | primary retains every valid pair; omission is not invalidation |
| SENS-LOO-P-04 | EXPLORATORY | P-04 | all admitted minus P-04 | 7 | 10.2857142857 | 1.91071428571 | `SENSITIVITY_ONLY_NOT_PRIMARY` | primary retains every valid pair; omission is not invalidation |
| SENS-LOO-P-05 | EXPLORATORY | P-05 | all admitted minus P-05 | 7 | 7.42857142857 | -0.946428571429 | `SENSITIVITY_ONLY_NOT_PRIMARY` | primary retains every valid pair; omission is not invalidation |
| SENS-LOO-P-06 | EXPLORATORY | P-06 | all admitted minus P-06 | 7 | 7.85714285714 | -0.517857142857 | `SENSITIVITY_ONLY_NOT_PRIMARY` | primary retains every valid pair; omission is not invalidation |
| SENS-LOO-P-07 | EXPLORATORY | P-07 | all admitted minus P-07 | 7 | 9.85714285714 | 1.48214285714 | `SENSITIVITY_ONLY_NOT_PRIMARY` | primary retains every valid pair; omission is not invalidation |
| SENS-LOO-P-08 | EXPLORATORY | P-08 | all admitted minus P-08 | 7 | 7.14285714286 | -1.23214285714 | `SENSITIVITY_ONLY_NOT_PRIMARY` | primary retains every valid pair; omission is not invalidation |

Primary N remains 8; primary mean remains `8.375` °C·s. The primary result is unchanged by every sensitivity computation.

## Mean versus median (TEST_ONLY)

| statistic | status | value | primary statistic | primary value | label | boundary |
|---|---|---:|---|---:|---|---|
| median | EXPLORATORY | 8.5 | mean | 8.375 | `SENSITIVITY_ONLY_NOT_PRIMARY` | primary mean unchanged |

## Extreme-pair influence (TEST_ONLY, EXTREME FIXTURE)

Fixture improvements: 3, 3, 3, 50

| sensitivity ID | status | omitted pair | valid N | mean without pair | delta | primary N | boundary |
|---|---|---|---:|---:|---:|---:|---|
| SENS-EXTREME-P-04 | EXPLORATORY | P-04 | 3 | 3 | -11.75 | 4 | extreme pair retained in the primary |

The extreme pair remains in the primary analysis; only the derived
sensitivity number omits it.

## Bootstrap versus parametric uncertainty (TEST_ONLY)

| role | method | lower | upper |
|---|---|---:|---:|
| PRIMARY | PAIRED_T_95_CI | 0.792153955753 | 15.9578460442 |
| SENSITIVITY | PAIR_BOOTSTRAP_PERCENTILE_95_CI | 2.5 | 14.125 |

Selection rule: `PREDECLARED_NO_FAVORABILITY_OR_WIDTH_SELECTION`; label `SENSITIVITY_ONLY_NOT_PRIMARY`; promotion allowed: false.
Sensitivity bootstrap settings: seed `20261110`, iterations 5000, research-grade true.

## Secondary outcome contrast (TEST_ONLY)

| outcome | status | role | N | shared pair IDs with primary | mean improvement | label | promotion allowed |
|---|---|---|---:|---:|---:|---|---|
| recovery_time | EXPLORATORY | secondary | 6 | 6 | 2.33333333333 | `SECONDARY_OUTCOME_NOT_PRIMARY` | false |

Contrast scope: Secondary outcome contrast only. It cannot be promoted to the primary result after inspecting outcomes. UNPAIRED_DESCRIPTIVE_CONTRAST_ON_DIFFERENT_PAIR_SETS.

## Multiple-comparison discipline

- primary hypothesis: the frozen primary physical outcome;
- frozen secondary outcomes: reported separately with their own N;
- exploratory sensitivity checks: labelled EXPLORATORY and never used
  as confirmation of the main project thesis.

The pure library cannot detect an exclusion omitted upstream: the
excluded-pair list must come from the complete W19 attempt ledger.
The W19-bound intake is a future, separately reviewed bridge.

## Unclosed scientific work

Real sensitivity tables cannot be produced until the final physical
pairs exist and the W20 gate authorizes analysis. Alternate-horizon
sensitivity requires the W13 horizon freeze and is refused here.
