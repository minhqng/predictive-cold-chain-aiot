# W23 figure inventory and scientific plot integrity

> **Task:** B-W23-03. This is a manifest-backed figure index. It does not create
> decorative substitutes for missing physical evidence.

```text
FIGURE_INVENTORY = DOCUMENTED
FINAL PHYSICAL FIGURES = WITHHELD
```

## 1. Canonical requirement matrix

| # | Required figure | Current artifact | Evidence class | Status | Scientific admissibility |
|---|---|---|---|---|---|
| F1 | Representative physical trajectories | `ml/reports/W05/physical-state-W05.svg` (diagnostic capture) | `PHYSICAL_MEASUREMENT_DIAGNOSTIC_ONLY` | `REPRODUCIBLE_BOUNDED_DEVICE_DIAGNOSTIC` | Diagnostic only; A ledger `INVALID`; not an accepted Controller A/B predictive trajectory |
| F1b | Accepted representative A/B physical trajectory | none | — | `WITHHELD_UNTIL_PHYSICAL_ANALYSIS` | Requires accepted physical data, trusted ordering and A/B provenance |
| F2 | PR curve | no committed curve image; synthetic AP metrics in W12/W14/W15 tables | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` | `REPRODUCIBLE_SOFTWARE_CONTROL` (tabular metric; curve not committed) | Synthetic development only; never a physical PR |
| F3 | Calibration curve (if applicable) | W14 calibration bins/folds CSVs; no reliability figure | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` | `NOT_APPLICABLE_RISK_SCORE_ONLY` | No probability semantics; a real reliability figure is not currently a valid model claim |
| F4 | EWT figure | none | — | `NOT_ESTIMABLE` | Real EWT is not estimable; no zero bar, histogram or proxy is substituted |
| F5 | Paired A/B effects | `ml/reports/W22/test-only-pair-plot-W22.svg` (toy fixture) | `SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY` | `REPRODUCIBLE_SOFTWARE_CONTROL` | Statistical-engine demonstration only, visibly `TEST_ONLY`; not a physical A/B result |
| F5b | Final physical paired effects | none | — | `WITHHELD_UNTIL_PHYSICAL_ANALYSIS` | W20 final analysis `LOCKED`; no accepted pairs |
| F6 | Outcome confidence interval | W22 report toy CI only | `SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY` | `WITHHELD_UNTIL_PHYSICAL_ANALYSIS` | No physical CI exists; the toy CI is not a substitute |

## 2. Figure records

### F1 — W05 physical-state diagnostic plot

| Field | Value |
|---|---|
| Figure ID | `FIG-W05-PHYSICAL-STATE` |
| Required scientific claim | physical-state channel behaviour of the recorded candidate capture |
| Source data identity | `evidence/A/W09/exports/CG-S1-H8C-600S.json`, SHA-256 `f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb`; A run index `eb71d3f5…` |
| Source evidence class | `PHYSICAL_MEASUREMENT_DIAGNOSTIC_ONLY`; admission `EXCLUDED_OR_BLOCKED` |
| Figure-generating code | `ml/scripts/real-data-qa-v1.py` SHA-256 `17fec358…`; renderer in `coldguard_ml` QA module |
| Figure SHA-256 | `c52f72d628122407…` |
| Plot availability | present (`ml/reports/W05/physical-state-W05.svg`) |
| Reproducibility status | `REPRODUCIBLE_WITH_COMMITTED_A_EXPORT` (A export is in tree and hash-verified) |
| Scientific admissibility | diagnostic only; boot `56044b74`; two unresolved run-ID segments in one boot |
| Limitations | not an independent run; not accepted A/B predictive evidence; T2 hot side excluded from chamber-air panels |

### F1b — Accepted representative physical trajectory

No figure exists. The figure requires accepted physical source data, trusted time
ordering and temperature/door/applied/power provenance for both controller arms.
The current candidate capture has an A ledger `INVALID`, unresolved run identity
and boot-scoped uptime. **Withheld.**

### F2 — PR curve

| Field | Value |
|---|---|
| Figure ID | `FIG-PR-SYNTHETIC` |
| Required scientific claim | synthetic development discrimination (AP / PR behaviour) |
| Source data identity | W11 synthetic fixture `W11_EXPANDED_SYNTHETIC_GROUPED`; metrics in `ml/reports/W12/grouped-metrics-W12.csv` and W15 `w15-manifest.json` |
| Source evidence class | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` |
| Figure-generating code | `ml/scripts/xgb-benchmark-W11.py`; `ml/src/coldguard_ml/grouped_evaluation.py` SHA-256 `89319d75…` computes `precision_recall_curve` |
| Source hash | W11 manifest `855c5beb…`; W15 manifest `3f1a1693…` |
| Plot availability | no committed PR curve image; AP/PR point counts are recorded (`pr_curve_points = 3` under saturation) |
| Reproducibility status | `REPRODUCIBLE_SOFTWARE_CONTROL` (metric reproducible; committed curve image not produced in W23) |
| Scientific admissibility | synthetic software control only; saturated AP = 1.0 |
| Limitations | no physical PR curve exists; the W16 locked test was not opened; a physical PR remains withheld |

### F3 — Calibration curve

W14 selected `RISK_SCORE_ONLY`. The synthetic calibration diagnostic is recorded
in `ml/reports/W14/calibration-summary-W14.json` and CSVs, but it is not a
validated real probability curve. A reliability figure as a model-validity claim
is **not applicable** while probability semantics are prohibited. Status:
`NOT_APPLICABLE_RISK_SCORE_ONLY`. A W14 synthetic calibration chart may be
referenced only with the precise `SYNTHETIC_SOFTWARE_CONTROL_ONLY` label; none is
committed as a figure.

### F4 — EWT / AIW

| Field | Value |
|---|---|
| Required claim | measured early-warning lead time / actionable intervention window |
| Source data identity | no qualified physical non-intervened trajectory with frozen warning and reactive anchors |
| Evidence class | `NOT_ESTIMABLE` |
| Plot availability | none |
| Status | `NOT_ESTIMABLE` |
| Limitations | W13/W14 conclude real EWT and AIW are not estimable; W22 refuses naive closed-loop EWT; no zero bar or histogram is fabricated |

W13 timing values (`command_to_thermal`, `door_to_critical`) are derived
truncation-biased proxies. They are proxy screening, not measured EWT or AIW, and
are not plotted as either.

### F5 — W22 TEST_ONLY pair plot

| Field | Value |
|---|---|
| Figure ID | `FIG-W22-TOY-PAIR` |
| Required claim | statistical-engine demonstration on a toy paired fixture |
| Source data identity | `ml/reports/W22/w22-manifest.json` toy fixtures, label `SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY`; 8 toy pairs |
| Source evidence class | `SYNTHETIC_STATISTICAL_UNIT_TEST_ONLY` |
| Figure-generating code | `ml/scripts/w22-statistics-contract-W22.py` SHA-256 `e61ebcfd…` |
| Figure SHA-256 | `e8b22bbc…` |
| Plot availability | present (`ml/reports/W22/test-only-pair-plot-W22.svg`) |
| Reproducibility status | `REPRODUCIBLE_SOFTWARE_CONTROL` |
| Scientific admissibility | statistical-engine demonstration only; visibly `TEST_ONLY`; every toy pair P-01…P-08 shown |
| Limitations | not a ColdGuard physical A/B result; may never be titled or captioned as final A/B improvement |

### F5b / F6 — Physical paired effects and outcome CI

Both are **withheld**. The W20 gate is `ANALYSIS_PREFLIGHT_BLOCKED`, the final
campaign is `NOT_AUTHORIZED`, the pair target is `UNKNOWN_UNFROZEN`, and zero
accepted physical pairs exist. The W22 toy CI
(`PAIRED_T_95_CI` on 8 toy pairs: mean 8.375, CI [0.7922, 15.9578]) is a
statistical-engine unit test, not a physical CI.

## 3. Plot integrity checks

Every committed figure was inspected against:

| Check | Result |
|---|---|
| Source identity and hash present | PASS for W05/W07/W09/W10/W22; see §2 |
| Correct time and metric units | PASS (seconds, °C, °C·s; no unlabeled axis) |
| Explicit evidence class on the figure | PASS (`DIAGNOSTIC ONLY`, `SOFTWARE-ONLY SYNTHETIC CONTROL`, `TEST_ONLY`) |
| Consistent A/B scales | PASS for the toy plot (single outcome axis); physical A/B plots absent |
| Correct sensor role labels | PASS: T1/T3/T4 chamber air; T2 TEC hot side excluded where appropriate |
| No misleading smoothing | PASS (no smoothing in W05/W07/W10/W22) |
| No unexplained truncated axes | PASS (axes are labelled; W09 overlay is explicitly diagnostic) |
| All admissible pairs shown | PASS for the toy plot (8/8); physical pair plot absent |
| No cherry-picked physical trajectories | PASS: no accepted physical trajectory figure exists |
| Uncertainty shown where appropriate | N/A for diagnostics; toy CI is textual, not a physical uncertainty figure |
| Figure manifest says PRESENT only when file exists | PASS; see §4 |

## 4. Figure manifest status

| Figure | File present | Manifest status |
|---|---|---|
| `ml/reports/W05/physical-state-W05.svg` | yes | `PRESENT` |
| `ml/reports/W07/phase-trajectories-W07.svg` | yes | `PRESENT` |
| `ml/reports/W09/baseline-comparison-W09.svg` | yes | `PRESENT` |
| `ml/reports/W10/feature-audit-W10.svg` | yes | `PRESENT` |
| `ml/reports/W10/real-diagnostic-W10.svg` | yes | `PRESENT` |
| `ml/reports/W22/test-only-pair-plot-W22.svg` | yes | `PRESENT` |
| Physical PR curve | no | `WITHHELD_UNTIL_PHYSICAL_ANALYSIS` |
| Real calibration reliability figure | no | `NOT_APPLICABLE_RISK_SCORE_ONLY` |
| Real EWT / AIW figure | no | `NOT_ESTIMABLE` |
| Final physical pair-effect figure | no | `WITHHELD_UNTIL_PHYSICAL_ANALYSIS` |
| Final physical outcome CI figure | no | `WITHHELD_UNTIL_PHYSICAL_ANALYSIS` |

## 5. Supplementary diagnostic figures (not canonical results)

| Figure | SHA-256 | Evidence class | Generating code |
|---|---|---|---|
| `ml/reports/W07/phase-trajectories-W07.svg` | `f7a09a4d…` | `PHYSICAL_MEASUREMENT_DIAGNOSTIC_ONLY` (one boot; repeatability `NOT_ESTABLISHED`) | `ml/scripts/plant-eda-W07.py` (`a1dc06e3…`) |
| `ml/reports/W09/baseline-comparison-W09.svg` | `63071abc…` | `SYNTHETIC_/DIAGNOSTIC_OVERLAY`; explicitly “NOT physical baseline evidence” | `ml/scripts/baseline-evaluation-W09.py` (`3a0ade52…`) |
| `ml/reports/W10/feature-audit-W10.svg` | `5fb7fd37…` | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` | `ml/scripts/feature-pipeline-W10.py` (`4d4b7bf9…`) |
| `ml/reports/W10/real-diagnostic-W10.svg` | `5e716c22…` | `PHYSICAL_MEASUREMENT_DIAGNOSTIC_ONLY`; “NOT eligible S2 evidence” | `ml/scripts/feature-pipeline-W10.py` (`4d4b7bf9…`) |

These figures are retained as diagnostic evidence. They are not substitutes for
the missing final physical figures.

## 6. Disposition

```text
B-W23-03 FIGURE INVENTORY = VERIFIED

B-W23-03 FINAL PHYSICAL FIGURES = WITHHELD

MISSING FINAL FIGURES:
  representative accepted A/B physical trajectories
  physical PR curve
  real calibration reliability curve
  real EWT / AIW figure
  final physical paired A/B effects
  final physical outcome confidence interval

NO DECORATIVE SUBSTITUTES WERE PRODUCED.
```

## 7. Binding sources

- `ml/reports/W05/physical-state-W05.svg`
- `ml/reports/W07/phase-trajectories-W07.svg`
- `ml/reports/W09/baseline-comparison-W09.svg`
- `ml/reports/W10/feature-audit-W10.svg`
- `ml/reports/W10/real-diagnostic-W10.svg`
- `ml/reports/W22/test-only-pair-plot-W22.svg`
- `ml/reports/W13/primary-horizon-decision.md`
- `ml/reports/W14/calibration-report.md`
- `ml/reports/W22/uncertainty-and-tests-W22.md`
- `ml/reports/W23/evidence-package-W23.json`
