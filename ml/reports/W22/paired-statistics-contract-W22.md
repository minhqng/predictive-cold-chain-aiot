# B-W22-01/04 — Paired descriptive statistics contract

> **SOFTWARE CONTRACT + TOY VERIFICATION ONLY.** Every numeric value in this
> report comes from an explicitly synthetic in-memory fixture labelled
> `SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY`. No physical A/B outcome was opened, and no
> real treatment effect, CI, p-value or physical claim is computed here.

## Scope and layer boundary

- **Layer A (pure library):** accepts in-memory numeric pairs, validates
  identities, computes descriptives, intervals, tests, effects and
  sensitivity. It has no file, campaign-export, telemetry, database or
  broker access and imports no file-reading module.
- **Layer B (this harness):** creates toy fixtures and writes reports.
- **Layer C (real analysis):** not implemented in W22; it requires the
  W20 campaign lock to authorize a separate execution plus a reviewed
  intake bridge.

## Statistical unit and sign convention

- Independent unit: one accepted matched Controller A/B pair.
- Frozen convention: `I_i = Y_A,i - Y_B,i` (lower-is-better outcomes).
- `I_i > 0` = Controller B improved; `I_i = 0` = no observed difference;
  `I_i < 0` = Controller B worsened.
- Telemetry rows, overlapping windows, repeated event samples, single
  arms, duplicated runs, bootstrap draws and attempts of one pair are
  never independent observations.

## Requirement coverage

| task | implementation | proof |
|---|---|---|
| B-W22-01 descriptive statistics | pair admission, `describe_pairs`, every-pair SVG | unit tests, reference table above, complete-pair plot |
| B-W22-02 95% CI | paired t interval, deterministic pair bootstrap | reference t criticals/CI, determinism, degenerate refusals |
| B-W22-03 test family | predeclared dispatcher (paired t, sign, Wilcoxon) | independent test references, license and no-selection probes |
| B-W22-04 effect size | native-unit mean, `d_z`, guarded relative reduction | paired-SD discrimination, zero-SD and denominator probes |
| B-W22-05 sensitivity | mean vs median, leave-one-out, influence, interval and secondary labels | primary-immutability tests and sensitivity report |
| B-W22-06 limitations | final-report template and interpretation categories | scientific-limitations report, `NO_INTERPRETATION_ANALYSIS_NOT_RUN` |

## Pair admission rules enforced by the engine

- exactly one Controller A arm and one Controller B arm per pair;
- unique pair ID, unique pair block, unique run ID across pairs;
- a rerun cannot become an additional independent pair;
- finite numeric outcomes only: missing values are not zero, NaN and
  infinity are refused, strings and booleans are refused;
- censored recovery and undefined energy outcomes are excluded upstream
  and never enter as numeric values;
- both arms and the dataset share the frozen native unit;
- admitted and excluded pairs are disjoint; exclusions are listed with
  reason codes, never silently dropped.

## Toy pair table (TEST_ONLY)

Outcome: `thermal_exposure` [°C·s] — role `PRIMARY`.

| pair | Controller A run | Controller B run | Y_A | Y_B | I_i | direction |
|---|---|---|---:|---:|---:|---|
| P-01 | TOY-S2-A-001 | TOY-S2-B-001 | 120 | 100 | 20 | B improved |
| P-02 | TOY-S2-A-002 | TOY-S2-B-002 | 120 | 115 | 5 | B improved |
| P-03 | TOY-S2-A-003 | TOY-S2-B-003 | 120 | 115 | 5 | B improved |
| P-04 | TOY-S2-A-004 | TOY-S2-B-004 | 120 | 125 | -5 | B worsened |
| P-05 | TOY-S2-A-005 | TOY-S2-B-005 | 120 | 105 | 15 | B improved |
| P-06 | TOY-S2-A-006 | TOY-S2-B-006 | 120 | 108 | 12 | B improved |
| P-07 | TOY-S2-A-007 | TOY-S2-B-007 | 120 | 122 | -2 | B worsened |
| P-08 | TOY-S2-A-008 | TOY-S2-B-008 | 120 | 103 | 17 | B improved |

## Toy summary statistics (TEST_ONLY)

| statistic | value |
|---|---:|
| valid pair count | 8 |
| excluded pair count | 0 |
| mean improvement | 8.375 |
| median improvement | 8.5 |
| sample SD (n-1) | 9.07016301633 |
| population SD (n) | 8.48436061233 |
| Q1 | 3.25 |
| Q3 | 15.5 |
| IQR | 12.25 |
| minimum | -5 |
| maximum | 20 |
| positive / zero / negative differences | 6 / 0 / 2 |
| direction | CONTROLLER_B_IMPROVED |
| distinct sessions / rig IDs | 1 / 1 |
| multi-site claim supported | false |

Quantile convention: `LINEAR_INTERPOLATION_TYPE7_HYNDMAN_FAN`. Pair ordering policy: `CANONICAL_SORT_BY_PAIR_ID`.

## Special cases (TEST_ONLY)

| fixture | N | mean | sample SD | direction | notes |
|---|---:|---:|---:|---|---|
| one pair | 1 | 4 | NOT_ESTIMABLE | CONTROLLER_B_IMPROVED | ONE_PAIR_DESCRIPTIVE_ONLY_NO_DISPERSION; N_BELOW_INFERENTIAL_MINIMUM |
| two pairs | 2 | 2 | 1.41421356237 | CONTROLLER_B_IMPROVED | N_BELOW_INFERENTIAL_MINIMUM |
| constant differences | 4 | 3 | 0 | CONTROLLER_B_IMPROVED | CONSTANT_PAIRED_DIFFERENCES_ZERO_DISPERSION |
| all zero differences | 3 | 0 | 0 | NO_OBSERVED_DIFFERENCE | CONSTANT_PAIRED_DIFFERENCES_ZERO_DISPERSION |
| negative improvement | 3 | -3 | 1 | CONTROLLER_B_WORSENED | — |
| mixed signs | 4 | 1.5 | 2.64575131106 | CONTROLLER_B_IMPROVED | — |

## Independent numerical verification

Reference values were calculated independently (hand formulas / a
trusted statistics library at authoring time) and are encoded in the
test suite; the driver re-checks them at generation time.

| check | expected | observed | tolerance | pass |
|---|---:|---:|---:|---|
| primary_mean | 8.375 | 8.375 | 1e-12 | true |
| primary_median | 8.5 | 8.5 | 1e-12 | true |
| primary_sample_sd | 9.07016301633 | 9.07016301633 | 1e-12 | true |
| primary_q1 | 3.25 | 3.25 | 1e-12 | true |
| primary_q3 | 15.5 | 15.5 | 1e-12 | true |
| reference_mean | 2.25 | 2.25 | 1e-12 | true |
| reference_median | 2.25 | 2.25 | 1e-12 | true |
| reference_sample_sd | 3.04822352636 | 3.04822352636 | 1e-12 | true |
| reference_population_sd | 2.89179874818 | 2.89179874818 | 1e-12 | true |
| reference_q1 | 0.375 | 0.375 | 1e-12 | true |
| reference_q3 | 4.25 | 4.25 | 1e-12 | true |
| t_critical_df7 | 2.36462425159 | 2.36462425159 | 1e-09 | true |
| t_statistic_primary | 2.61164844856 | 2.61164844856 | 1e-12 | true |
| t_p_primary | 0.0348297081712 | 0.0348297081712 | 1e-12 | true |
| t_ci_lower_primary | 0.792153955753 | 0.792153955753 | 1e-11 | true |
| t_ci_upper_primary | 15.9578460442 | 15.9578460442 | 1e-11 | true |
| sign_p_primary | 0.2890625 | 0.2890625 | 1e-12 | true |
| wilcoxon_p_primary | 0.0625 | 0.0625 | 1e-12 | true |
| effect_dz_primary | 0.923357164024 | 0.923357164024 | 1e-12 | true |
| secondary_mean | 2.33333333333 | 2.33333333333 | 1e-12 | true |
| secondary_sample_sd | 2.58198889747 | 2.58198889747 | 1e-12 | true |

## Effect size (TEST_ONLY)

- outcome: `thermal_exposure` [°C·s] — SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY
- native-unit absolute improvement: `8.375` °C·s
- standardized paired effect `d_z = mean(I) / SD(I)`: `0.923357164024` (DEFINED)
- relative reduction: `0.0697916666667` (DEFINED)
- toy denominator floor: `5` °C·s — **toy demonstration only, not a frozen physical value**
- direction: `CONTROLLER_B_IMPROVED`

A synthetic d_z is a mathematical test result, not a physical effect
estimate; a zero or near-zero denominator never yields an infinite or
misleading percentage.

## Every-pair visualization

`test-only-pair-plot-W22.svg` draws all 8 pairs once, with Controller A
circles, Controller B squares, improvement direction by colour, pair
identity in each element title, the primary role label and a permanent
`TEST_ONLY` banner. No average-only bar chart is produced.

## Unclosed scientific work

The real descriptives for accepted physical pairs cannot be produced
until the W20 campaign gate authorizes a separate execution and A/C/D
supply the frozen outcomes with accepted source hashes.
