# B-W22-02/03 — 95% confidence intervals and predeclared test family

> **SOFTWARE CONTRACT + TOY VERIFICATION ONLY.** No physical outcome was
> opened and no real CI or p-value exists.

## Student-t critical values (independent references)

| df | t(0.975, df) computed | reference | pass |
|---:|---:|---:|---|
| 1 | 12.7062047362 | 12.7062047362 | true |
| 4 | 2.7764451052 | 2.7764451052 | true |
| 7 | 2.36462425159 | 2.36462425159 | true |
| 9 | 2.2621571628 | 2.2621571628 | true |
| 19 | 2.09302405441 | 2.09302405441 | true |
| 100 | 1.98397151852 | 1.98397151852 | true |

The small-N interval uses the Student-t critical value, never an
automatic 1.96; the degrees of freedom are `n - 1`.

## Primary paired t interval (TEST_ONLY)

- method: `PAIRED_T_95_CI` — role `PRIMARY`
- declared primary method: `PAIRED_T_95_CI` (freeze id `W22-TOY-CI-FREEZE-20261110`)
- exactly one primary interval: `PAIRED_T_95_CI`
- N: 8, df: 7
- mean improvement: `8.375` °C·s
- sample SD: `9.07016301633`
- standard error: `3.20678688766`
- critical value: `2.36462425159`
- 95% CI: [`0.792153955753`, `15.9578460442`] °C·s
- research-grade settings: true

## Pair-level bootstrap (TEST_ONLY, SENSITIVITY ROLE)

- role: `SENSITIVITY` — a second interval method is always
  labelled sensitivity and can never be primary by width or favour.
- statistic: `MEAN`
- resampling unit: `COMPLETE_MATCHED_PAIRS` — complete matched pairs
- seed: `20261110`, iterations: 5000, quantile convention: `LINEAR_INTERPOLATION_TYPE7_HYNDMAN_FAN`
- RNG: `PYTHON_RANDOM_MT19937_RANDOM_SEQUENCE_V1`
- percentile 95% CI: [`2.5`, `14.125`] °C·s
- draw digest: `f7385a6d9c4493b8f2f82cf8ef9899331fd52a55b6831a00f1994c4930a584ef`
- research-grade settings: true

The canonical final setting is at least 2,000 iterations, preferably
5,000–10,000, with a recorded seed. A and B arms are never resampled
independently, and telemetry windows are never resampling units.

Interval policy: exactly one predeclared primary interval per outcome.
The bootstrap can be reported as the labelled sensitivity interval; it
cannot become primary by being narrower or more favourable.

## Degenerate cases (TEST_ONLY)

| fixture | method | status | reason |
|---|---|---|---|
| one pair | paired t | NOT_ESTIMABLE | CI_NOT_ESTIMABLE_INSUFFICIENT_PAIRS |
| two pairs | paired t | NOT_ESTIMABLE | CI_NOT_ESTIMABLE_INSUFFICIENT_PAIRS |
| constant differences | paired t | NOT_ESTIMABLE | CI_NOT_ESTIMABLE_ZERO_DISPERSION |
| constant differences | bootstrap | NOT_ESTIMABLE | CI_NOT_ESTIMABLE_ZERO_DISPERSION |

A constant (zero-width) interval is reported as the constant with an
explicit refusal, never as perfect scientific certainty.

## Predeclared paired test family

Supported methods: paired t-test, exact sign test, Wilcoxon signed-rank
under its licensed assumption, and pair-level bootstrap uncertainty.
The dispatcher runs exactly one declared family. It has no API that
compares candidate p-values, and no code path selects the smallest p.
A fallback runs only when the preferred method is not estimable with
the exact predeclared reason code, the fallback family's assumption
license is declared, and the diagnostic evidence is recorded. No
normality test is implemented, so a failed normality check can never
be used as an automatic switch to a favourable method.

Declaration: preferred family `PAIRED_T`, method freeze id `W22-TOY-METHOD-FREEZE-20261110`, alternative `two-sided`, assumption license `PAIRED_T_SYMMETRY_OR_NORMALITY_LICENSED` (toy declaration only).

| field | value |
|---|---|
| family | PAIRED_T |
| status | ESTIMABLE |
| paired differences used | 8 pairs / 8 differences |
| statistic (t) | 2.61164844856 |
| degrees of freedom | 7 |
| p-value (two-sided, toy) | 0.0348297081712 |
| claim boundary | `TEST_STATISTIC_ONLY_NOT_A_PHYSICAL_CLAIM` |

A low toy p-value is not a physical effect, not practical significance
and not a declaration of physical superiority.

### Predeclared fallback demonstration (TEST_ONLY)

The t-test is not estimable for constant differences; the declaration
predeclares the exact sign test with the recorded reason and license.

| field | value |
|---|---|
| preferred failure | `TEST_NOT_ESTIMABLE_ZERO_DISPERSION` |
| fallback family | SIGN_TEST |
| fallback applied | true |
| fallback p-value (toy) | 0.125 |

## Independent test verification

| check | expected | observed | tolerance | pass |
|---|---:|---:|---:|---|
| t_statistic_primary | 2.61164844856 | 2.61164844856 | 1e-12 | true |
| t_p_primary | 0.0348297081712 | 0.0348297081712 | 1e-12 | true |
| sign_p_primary | 0.2890625 | 0.2890625 | 1e-12 | true |
| wilcoxon_p_primary | 0.0625 | 0.0625 | 1e-12 | true |

Wilcoxon exact p-values use midranks and the exact sign-flip
permutation distribution (n_eff <= 16); above that, a tie-corrected
normal approximation with continuity correction is used. Zero
differences are dropped and reported as `n_zero`. For tied
absolute differences the midrank permutation value is the reference;
a forced-exact library call that re-ranks ties without midranks
can report a different number and is not used here.

## Unclosed scientific work

The real primary CI, real test result and real bootstrap interval
remain withheld until the W20 gate authorizes a separate execution and
the frozen outcome export is admitted.
