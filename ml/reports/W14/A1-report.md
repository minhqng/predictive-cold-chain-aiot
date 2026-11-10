# W14 A1 — one chamber-air sensor versus three

**Task:** B-W14-01 · **Layer:** `coldguard-w14-role-correct-ablation-v1`
**Scientific evidence class: `SYNTHETIC_SOFTWARE_CONTROL_ONLY`.**
**Verdict: `SOFTWARE_VERIFIED` / `NOT_ESTABLISHED` for any physical claim.**

> This report measures software behaviour on the deterministic W11 synthetic
> fixture. It is not a physical predictive result and does not establish that
> three sensors are better, worse or equivalent on the real plant.

## 1. Question and role reconciliation

Canonical Doc 03 §61 and Doc 05B §42 describe A1 as "one designated T" versus
the abstract example "T1/T2/T3 + spatial features". The observed rig in the
frozen W10 registry is not that abstract numbering:

| Slot | Registry role | In chamber-air aggregate |
|---|---|---|
| T1 | `CHAMBER_CENTER` | yes |
| T2 | `TEC_HOT_SIDE` | **no** |
| T3 | `CHAMBER_BOTTOM` | yes |
| T4 | `CHAMBER_NEAR_DOOR` | yes |

**Reconciliation:** the canonical three-temperature arm is implemented as the
three role-qualified chamber-air probes **T1/T3/T4**. T2 is the TEC hot side
and is never chamber air. The abstract example is not authority to include the
hot-side probe. This is recorded as a canonical reconciliation, not a sensor
relabeling.

Doc 00 §2.2 contains an early planning map (`T1` near door, `T2` central,
`T3` far) and explicitly says it is "subject to final physical placement
freeze in Doc 01". The as-built authority is the operator-frozen placement in
`evidence/A/W07/geometry-v1.md` and `evidence/A/W07/handoff.md` ("T1 centre,
T2 TEC hot side, T3 bottom, T4 near door"), corroborated by the W07
probe-identification logs (`t2_role=HOT_SIDE`,
`mandatory_roles=HOT_SIDE`). The frozen W10 registry encodes that as-built
map. Doc 00 §2.2 is therefore a superseded planning sketch, not the W14 role
authority.

**A1a single probe (predeclared): `CHAMBER_CENTER` (T1).** The choice is fixed
by role semantics before any W14 outcome is computed: it is the central
chamber-air role, not the door-adjacent probe, not the bottom probe and not the
hot side. No outcome-based probe selection was performed.

## 2. Comparison contract

| Requirement | A1a | A1b |
|---|---|---|
| Feature view | `coldguard-w14-a1a-single-center-v1` | `coldguard-w14-a1b-three-chamber-air-v1` |
| Chamber-air thermal sources | CHAMBER_CENTER only | T1/T3/T4 |
| Non-thermal context | 14 W11 context features | identical 14 W11 context features |
| Development split | W11 8 pairs / 16 runs | identical |
| CV folds | W11 4 grouped folds, seed 42 | identical |
| Label / horizon | `coldguard-w11-development-label-v1`, H = 60 s reference | identical |
| Model family / params | XGBoost, W11 `xgb-v1-config.yaml` | identical |
| Strategies | UNWEIGHTED, TRAIN_FOLD_CLASS_WEIGHT | identical |
| Evaluation rules | W11 AP + event metrics + censoring | identical |
| Population | 1936 windows (480 pos / 1456 neg) | identical |
| Random seed policy | W11 seed 42 | identical |

The evaluable population identity hash is identical across every arm:
`6d6d265d03bd664bd808652789c48af3c79a508c01625bc445f5c5c427f4f889`.
Labels are generated independently of features, so missing feature values
become NaN and never change sample eligibility. Only the chamber-air thermal
sensing family varies; door, actuation, electrical and environment features are
held identical.

**Scope note:** the 14 context features include the BME280
`ambient_temperature_c` and `relative_humidity_pct`. They are environmental
context from a separate sensor, present identically in both arms; they are not
chamber-air probes and are not part of the "one versus three" chamber-air
sensing contrast. A1a's chamber-air thermal family contains only
`CHAMBER_CENTER`-derived features.

## 3. Feature allowlists and provenance

### A1a — 21 features

Thermal (7):

```text
T_center_c
A1A_single_center_rolling_mean_temperature_60s
A1A_single_center_rolling_std_temperature_60s
A1A_single_center_rolling_min_temperature_60s
A1A_single_center_rolling_max_temperature_60s
A1A_single_center_past_only_slope_c_per_min_60s
A1A_single_center_past_only_temperature_delta_60s
```

Context (14, identical to A1b): `door_open`, `time_since_open`,
`duration_so_far`, `count_past_60s`, `applied_cooling`, `applied_duty`,
`time_since_confirmed_applied_change`, `cooling_voltage_v`,
`cooling_current_a`, `cooling_power_w`, `energy_counter_wh`,
`past_integrated_cooling_energy_wh`, `ambient_temperature_c`,
`relative_humidity_pct`.

The six `A1A_*` rolling features reuse the frozen formulas but apply them to
`CHAMBER_CENTER` only. The frozen registry lists `t1_c;t3_c;t4_c` as the base
formula sources; the view's source binding is `CHAMBER_CENTER` and the new
feature id prevents the single-probe column from masquerading as a multi-probe
aggregate. The W10 registry file is unchanged.

Excluded from A1a, with reasons:

| Excluded | Reason |
|---|---|
| `T_bottom_c`, `T_near_door_c` | other chamber-air probes |
| `T_chamber_max_c`, `T_chamber_min_c`, `T_chamber_mean_c`, `T_chamber_spread_c` | multi-probe aggregates / spatial statistic |
| `past_only_spatial_spread_60s` | multi-probe spatial statistic, undefined for one sensor |
| `T_tec_hot_side_c` | TEC hot side, not chamber air |

### A1b — 28 features

Exactly the frozen W11 allowlist: the 7 A1a thermal features plus 7 additional
W11 thermal features — four multi-probe aggregates (`T_chamber_max_c`,
`T_chamber_min_c`, `T_chamber_mean_c`, `T_chamber_spread_c`), two other-probe
instantaneous features (`T_bottom_c`, `T_near_door_c`) and one multi-probe
spatial spread (`past_only_spatial_spread_60s`) — plus the same 14 context
features. `T_tec_hot_side_c` is excluded.

### Provenance audit

Full feature-by-feature source mapping: `A1-feature-provenance-W14.csv`
(SHA-256 `64b377f956725c8899681be1620a986e24d1889e6994695a73230ae864d4124a`).
The audit confirmed:

- every A1a thermal feature binds `CHAMBER_CENTER` and nothing else;
- no A1a feature traces to `t2_c`, `T_tec_hot_side_c`, `T_chamber_*` or
  `past_only_spatial_spread_60s`;
- the multi-probe rolling base definitions are used only through the declared
  single-role view transform, with distinct feature ids;
- mutating T3, T4 and the hot side by +1000 °C leaves every A1a value and
  missing-reason unchanged; the same mutation changes A1b. The dynamic probe is
  `single_probe_isolation_probe` and is covered by tests;
- no future information is consumed: all lookbacks are `(t - 60 s, t]` and the
  labels are generated after the feature rows.

## 4. Population and support

| Quantity | Value |
|---|---|
| Development runs | 16 (8 S1 + 8 S2) |
| Effective independent groups | 8 pairs |
| Grouped folds | 4 (seed 42) |
| Evaluable windows | 1936 (480 positive, 1456 negative) |
| Censored exclusions | 960 |
| Untrusted-label exclusions | 0 |
| Locked test runs | `CG-W11-S1-001`, `CG-W11-S1-002`, `CG-W11-S2-001`, `CG-W11-S2-002` — untouched |

Per-run support is identical across arms: each S1 run contributes 121 negative
windows; each S2 run contributes 60 positive and 61 negative windows. Positive
support is spread over all 8 independent S2 runs (60/480 = 12.5% each), not
concentrated in one correlated run. Full support: `A1-support-W14.csv`
(SHA-256 `8dc6ff0d37f92dc4eebf91e436eee781f1b7b6224ae7834321bb53a908e4058f`).

## 5. Fold and event results

Both strategies fitted all four folds. Every fold validation has 484 windows
(120 positive / 364 negative); training has 1452 windows (360 / 1092).

| Arm | Strategy | Fold AP F1/F2/F3/F4 | OOF AP | Event recall | False warnings/h | Missed events |
|---|---|---|---:|---:|---:|---:|
| A1A | UNWEIGHTED | 1.0000 / 1.0000 / 1.0000 / 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| A1A | TRAIN_FOLD_CLASS_WEIGHT | 1.0000 / 1.0000 / 1.0000 / 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| A1B | UNWEIGHTED | 1.0000 / 1.0000 / 1.0000 / 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| A1B | TRAIN_FOLD_CLASS_WEIGHT | 1.0000 / 1.0000 / 1.0000 / 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |

Per fold, each arm produced 2 warning episodes, matched 2 critical events,
0 unmatched warnings and 0 missed events. Full rows:
`A1-fold-metrics-W14.csv` (SHA-256
`066e38c98645bf85f1512002f2902b15687206860b1b9abb0a252fe0d36a6149`).

### Paired fold comparison

`A1-paired-folds-W14.csv` (SHA-256
`faf1fb6a7986d84ea66fc3eb8a529cd98604ed283eabdbc564a90613278409a0`)
pairs A1a/A1b by fold and strategy. Every fold has `delta_ap_b_minus_a = 0.0`,
identical event recall, zero false warnings and zero missed events.

## 6. Effect direction and uncertainty

- Point estimate: **no measurable AP difference** in any of the four grouped
  folds for either strategy (delta = 0.0000).
- This is not evidence of equivalence, and not evidence of three-sensor
  superiority. It is a saturated synthetic control: both arms already contain
  the door/actuation context, and the fixture's thermal signal is strongly
  scenario-identifying.
- Four correlated grouped folds over 8 pairs do not provide a confidence
  interval or a significance test. No p-value is reported.
- The effect uncertainty for the real plant is **not estimable** because there
  are 0 real predictive-eligible runs.

## 7. Exclusions and limitations

- 960 windows are right-censored because `t + 60 s` exceeds the fixture
  coverage; they are excluded, never labeled negative.
- 0 windows are excluded for untrusted labels.
- The synthetic fixture's data-generating process does not approximate the
  six-litre plant.
- No real physical data was borrowed, inspected or modified.
- The locked synthetic test pair was not opened.
- AP = 1.0 is a software-control artefact, not a ColdGuard predictive result.
- The single-probe choice is a predeclared role decision, not an outcome-based
  selection.

## 8. Reproduction and binding

```bash
cd ml
uv run --locked --python 3.12 python scripts/w14-ablation-W14.py
```

| Binding | Value |
|---|---|
| W14 manifest | `w14-manifest.json` SHA-256 `e4a0263ead067a10df8d23ffc2bb10d6e750c88e515153fd6f637c733077357d` |
| Base revision | `824a5389c29ade0e56ecef7ef21eb35c2a379a7b` |
| W10 registry | `1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9` |
| W11 model config | `4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a7660dd6481ee1f71a84` |
| W13 input manifest | `02a76660319f6118900ec54ee3d50fa96968ad14b0a7110f3fdaf1b62417a404` |
| Reference horizon | 60 s, `ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN` |
| Analysis code | `c415d74469e8e1a3fa0c693765a8c2f3a185562df382249fa8f959f367dfbe2c` |

## 9. Unresolved questions

- Would the A1 contrast change under a real eligible population with frozen
  target and horizon? **Not estimable now.**
- Are the three chamber-air roles independently calibrated on the real rig?
  **No calibration traceability exists** (`calibration_id = UNRECORDED`).
- Is the near-door probe's synthetic advantage an artefact of the fixture
  generator? **Yes for this fixture; it cannot be extrapolated.**
