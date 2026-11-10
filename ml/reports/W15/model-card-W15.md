# W15 model card — synthetic XGBoost development candidate

**Task:** B-W15-05 · **Artifact:** `coldguard-w15-synthetic-xgb-candidate-v1`
**Evidence class: `SYNTHETIC_SOFTWARE_CONTROL_ONLY` · Release eligibility: `NON_DEPLOYABLE_CANDIDATE`.**

> This card describes the model that was actually produced in W15, not an imagined
> future model. The artifact is a risk-score development candidate trained on a
> deterministic synthetic fixture. It is not approved for physical control,
> calibrated probabilities or public early-warning claims.

## 1. Model identity

| Field | Value |
|---|---|
| Model family | XGBoost (`binary:logistic`, `tree_method=hist`) |
| Primary native format | `model.ubj` |
| Secondary native format | `model.json` |
| Model SHA-256 (`model.ubj`) | `25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f` |
| `model.json` SHA-256 | `67eef303104bca00a8a1669dcacf6b7ff08219fff493a99280d27086875f2efd` |
| Artifact manifest SHA-256 | `85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e` |
| Library version | xgboost 3.4.1; scikit-learn 1.9.1; numpy 2.5.3; pandas 3.0.6; Python 3.12 |
| Config version / hash | `coldguard-xgb-v1-development-v1` / `4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a7660dd6481ee1f71a84` |
| Feature version / hash | `CG-FEAT-1.0` / `1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9` |
| Output semantics | `risk_score` only |
| Calibration status | `RISK_SCORE_ONLY` |
| Operating threshold | 0.5, `ILLUSTRATIVE_NOT_FROZEN` |
| Warning persistence | `NOT_FROZEN` |

Ordered features (28, frozen W11 order):

```text
T_chamber_max_c, T_chamber_min_c, T_chamber_mean_c, T_chamber_spread_c,
T_center_c, T_bottom_c, T_near_door_c,
rolling_mean_temperature_60s, rolling_std_temperature_60s,
rolling_min_temperature_60s, rolling_max_temperature_60s,
past_only_slope_c_per_min_60s, past_only_temperature_delta_60s,
past_only_spatial_spread_60s,
door_open, time_since_open, duration_so_far, count_past_60s,
applied_cooling, applied_duty, time_since_confirmed_applied_change,
cooling_voltage_v, cooling_current_a, cooling_power_w,
energy_counter_wh, past_integrated_cooling_energy_wh,
ambient_temperature_c, relative_humidity_pct
```

The model refuses any other feature identity or order through its guarded interface.
The raw booster bypasses schema checks and is not an approved inference path; raw
native load is prohibited. T2 TEC hot side is not a feature.

The 16 required metadata fields from the W15 brief are all present in
`model/model-manifest-W15.json`; additional fields record provenance detail.

## 2. Training provenance

| Item | Value |
|---|---|
| Dataset | `W11_EXPANDED_SYNTHETIC_GROUPED` |
| Fixture version | `coldguard-w11-synthetic-grouped-v1` |
| Source type | deterministic synthetic software fixture |
| Development runs | 16 (8 S2 + 8 S1) |
| Independent groups | 8 pairs |
| Partitions used | train + validation only |
| Locked test used | **no** |
| Training windows | 1936 (480 positive / 1456 negative) |
| Strategy | `UNWEIGHTED` (`scale_pos_weight = 1.0`) |
| Training code revision | `9027c469a82859b4eb2dcf5b4d8255bf1f59c641` (generation base) |

The artifact was refit on all 16 development runs after the grouped evaluation. It
was not re-scored as a new performance estimate; the reported metrics come from the
grouped CV of the A3b arm.

## 3. Intended use

- Offline software-control experiments on the W11 synthetic fixture.
- Risk-score ranking with explicit `risk_score` semantics.
- A future shadow-inference candidate only after all release gates in §8.

## 4. Not approved for

- Physical Controller B actuation.
- Calibrated-probability, percentage-risk or "P(critical)" wording.
- Public reliability or real-world early-warning superiority claims.
- Final A/B comparison or physical benefit claims.
- Registration, deployment or activation in C's backend.

## 5. Target and horizon

| Item | Status |
|---|---|
| Label spec | `coldguard-w11-development-label-v1` |
| Horizon | 60 s, `ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN` |
| Critical target / representative temperature | `DEVELOPMENT_CANDIDATE_NOT_SELECTED` |
| Primary horizon frozen | **no** |
| Critical criterion frozen | **no** |

The 60 s value is a software-development reference inherited from W11. It is not a
physically justified primary horizon and must not be promoted silently.

## 6. Evaluation

Synthetic grouped CV, 4 folds, seed 42, matched A3 population:

| Metric | A3a (20 features) | A3b (28 features, artifact identity) |
|---|---:|---:|
| OOF AP (UNWEIGHTED) | 1.0000 | 1.0000 |
| OOF AP (weighted) | 1.0000 | 1.0000 |
| Fold AP range | 1.0000–1.0000 | 1.0000–1.0000 |
| Event recall | 1.0000 | 1.0000 |
| False warning episodes/hour | 0.0000 | 0.0000 |
| Missed critical events | 0 | 0 |

These numbers are saturated software controls. A1/A2/A3 findings:

- A1: `SOFTWARE_VERIFIED` (three role-qualified chamber-air probes vs one).
- A2: `SOFTWARE_VERIFIED` (thermal vs thermal + door) with a scenario-identification trap.
- A3: `SOFTWARE_VERIFIED`; physical effect `NOT_ESTABLISHED`; both arms saturate and
  the fixture electrical block is run-invariant.

### Native model inspection (diagnostic only)

The fitted candidate has 60 trees and 60 splits. Every split is on `time_since_open`
(feature index 15, threshold 60 s); the other 27 features, including all eight
electrical/applied-state features, are unused. The artifact is therefore a door-time
rule induced by the synthetic fixture, not a learned thermal/electrical early-warning
function. Split usage is not causal importance and is not evidence about a real plant.
Full detail: `A3-model-inspection-W15.json`.

Undefined/unknown values are reported as undefined; none is turned into zero.

## 7. Missingness and failure behaviour

| Situation | Behaviour |
|---|---|
| Stale/untrusted thermal sensor | thermal feature missing per frozen registry rule; no silent fill |
| PZEM `UNKNOWN`/`INVALID`/`DEGRADED` | electrical feature missing; never zero and never VALID |
| Counter reset/rollover | `MISSING_COUNTER_RESET`; no negative consumption |
| Power discontinuity or gap > 5 s | integrated energy missing; never bridged |
| Incomplete window | feature missing; sample eligibility unchanged |
| Door state `UNKNOWN` | door feature missing, never CLOSED |
| Invalid run identity | data path refuses admission rather than guessing |
| Feature order/identity mismatch | guarded artifact refuses prediction |
| Model byte hash mismatch | guarded loader refuses the artifact |
| Corrupted model bytes | native load fails closed |
| Unsupported operating domain / missing evidence | risk score is not a claim of validity; no prediction is promoted to physical evidence |

The artifact's guarded interface requires the exact 28 ordered columns; missing,
extra or reordered columns raise an error.

## 8. Limitations

- Synthetic scenario-identification bias; the fixture generator determines the signal.
- The fitted artifact is a one-feature door-time rule (`time_since_open`); it does not
  demonstrate thermal or electrical learning.
- Small synthetic population: 8 pair groups, 4 correlated folds.
- No real predictive-eligible development population (0 runs).
- No real calibration population; risk score only.
- No real event/latency/EWT/AIW evidence.
- Possible controller-action shortcut through applied-state features.
- Cumulative energy features can act as run-age identifiers.
- Branch energy is not whole-system energy; PWM-sampled power is meter-dependent.
  PWM characterization is an A-owned W16 precondition before PZEM power/energy may be
  used as primary evidence.
- A current reading is not proof of thermal cooling.
- The artifact is not threshold- or persistence-frozen.

## 9. Next release gates

1. Admissible real grouped development population.
2. Physically justified primary horizon and frozen critical target.
3. Frozen operational policy (threshold and persistence).
4. Score/calibration decision with a real calibration population.
5. Accepted model/feature identity and a reproducible artifact.
6. W16 locked test, evaluated once without retuning.
7. C/D shadow and authorization gates.

## 10. Binding

- W15 manifest SHA-256: `3f1a16939e1c16345e9948eb109085d123d3e57a57717132b0ab9c2d89d5eafa`
- Artifact manifest: `model/model-manifest-W15.json`
- A3 report: `A3-report.md`
- Prediction/diagnosis assessment: `prediction-vs-diagnosis-W15.md`
