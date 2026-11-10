# W14 A2 — thermal versus thermal + door

**Task:** B-W14-02 · **Layer:** `coldguard-w14-role-correct-ablation-v1`
**Scientific evidence class: `SYNTHETIC_SOFTWARE_CONTROL_ONLY`.**
**Verdict: `SOFTWARE_VERIFIED` / `NOT_ESTABLISHED` for early physical prediction.**

> A2 is a software-control comparison on a deterministic synthetic fixture whose
> door pattern is part of the data-generating process. A near-perfect AP does not
> prove that door context enables early physical prediction.

## 1. Comparison arms

| Arm | View | Features | Content |
|---|---|---|---|
| A2a | `coldguard-w14-a2a-thermal-v1` | 14 | thermal only |
| A2b | `coldguard-w14-a2b-thermal-door-v1` | 18 | exactly the same 14 thermal features + 4 authorized door features |

The shared thermal set is the 14 frozen W10 thermal features:
`T_chamber_max_c`, `T_chamber_min_c`, `T_chamber_mean_c`,
`T_chamber_spread_c`, `T_center_c`, `T_bottom_c`, `T_near_door_c`,
`rolling_mean_temperature_60s`, `rolling_std_temperature_60s`,
`rolling_min_temperature_60s`, `rolling_max_temperature_60s`,
`past_only_slope_c_per_min_60s`, `past_only_temperature_delta_60s`,
`past_only_spatial_spread_60s`.

The A2b delta is exactly the four existing MC-38 identities:

```text
door_open
time_since_open
duration_so_far
count_past_60s
```

No replacement door feature is invented. Electrical, applied-state and
environmental context are excluded from **both** arms; A3 owns the electrical
contrast in W15.

## 2. Trust boundary

The door view inherits the frozen registry trust rule: trusted only when the
state is `OPEN` or `CLOSED`, door quality is `VALID`, and polarity is attested.
`UNKNOWN` is missing, **never CLOSED**. No door feature is inferred from thermal
data.

| Feature | Missing behaviour (frozen policy) |
|---|---|
| `door_open` | missing for UNKNOWN, untrusted quality or missing polarity attestation |
| `time_since_open` | missing when no trusted opening transition has been observed in the boot |
| `duration_so_far` | missing while UNKNOWN, after an UNKNOWN interruption, or when the sequence starts OPEN without an observed edge; 0 only for trusted CLOSED |
| `count_past_60s` | counts trusted transitions only; never crosses a boot boundary; duplicate deliveries never create transitions |

Dynamic verification used a fixture with an UNKNOWN door window at
52–56 s and a fixture with unattested polarity:

- at anchors 52–56 s, `door_open` and `duration_so_far` are `None` with reason
  `MISSING_UNKNOWN_DOOR`; no value is converted to `0.0` (CLOSED);
- at a trusted CLOSED anchor (39 s), `door_open = 0.0` with reason `PRESENT`;
- with `door_polarity_attested=False`, every `door_open` value is `None` with
  reason `MISSING_POLARITY_UNATTESTED`;
- A2a is unaffected by door-state, polarity, electrical or environment
  mutation; the thermal-only arm contains no door feature and no context.
- A2b is unaffected by electrical/applied-state/environment mutation (the
  electrical columns are absent), so the A2 contrast is not silently changed by
  unrelated context.

## 3. Controlled experiment

Both arms use the identical W11 development split, 4 grouped folds (seed 42),
label identity (`coldguard-w11-development-label-v1`, H = 60 s reference), XGBoost
parameters, risk threshold, imbalance strategies and evaluation rules. The
evaluable population is matched window-for-window:
1936 windows (480 positive / 1456 negative), 960 censored, 0 untrusted. The
population identity hash is
`6d6d265d03bd664bd808652789c48af3c79a508c01625bc445f5c5c427f4f889`.

Locked test runs `CG-W11-S1-001`, `CG-W11-S1-002`, `CG-W11-S2-001`,
`CG-W11-S2-002` remain untouched.

## 4. Positive support

| Quantity | Value |
|---|---|
| Positive windows | 480 |
| S2 runs with positives | 8 |
| Positives per S2 run | 60 |
| Largest single-run positive share | 60 / 480 = 12.5% |
| Negative windows | 1456 (S1 runs: 121 each) |

Positive examples are distributed across eight independent S2 runs, not
concentrated in one correlated run. Support file:
`A2-support-W14.csv` (SHA-256
`8dc6ff0d37f92dc4eebf91e436eee781f1b7b6224ae7834321bb53a908e4058f`).

## 5. Fold and event results

| Arm | Strategy | Fold AP F1/F2/F3/F4 | OOF AP | Event recall | False warnings/h | Missed events |
|---|---|---|---:|---:|---:|---:|
| A2a | UNWEIGHTED | 1.0000 / 1.0000 / 1.0000 / 1.0000 | 0.999987 | 1.0000 | 0.0000 | 0 |
| A2a | TRAIN_FOLD_CLASS_WEIGHT | 1.0000 / 1.0000 / 1.0000 / 1.0000 | 0.999970 | 1.0000 | 0.0000 | 0 |
| A2b | UNWEIGHTED | 1.0000 / 1.0000 / 1.0000 / 1.0000 | 1.000000 | 1.0000 | 0.0000 | 0 |
| A2b | TRAIN_FOLD_CLASS_WEIGHT | 1.0000 / 1.0000 / 1.0000 / 1.0000 | 1.000000 | 1.0000 | 0.0000 | 0 |

Full rows: `A2-fold-metrics-W14.csv` (SHA-256
`302b5716ef1be068af541d8c5c6523c5f80be8e845ad0af1ef1bd3b94cac726e`).
Paired fold deltas: `A2-paired-folds-W14.csv` (SHA-256
`f892553db71766608772d2f22250e7447e565c0edbd80b128ab92e9714475207`).
Every per-fold AP delta is 0.0000; the only non-zero difference is the pooled
OOF value: +1.302e-05 for UNWEIGHTED and +3.049e-05 for the weighted strategy.

## 6. Scenario-identification trap

The synthetic fixture's thermal signal already identifies the scenario:

- the S2 thermal trajectory rises at the door opening and decays afterwards;
- the near-door probe is `+0.8 °C` while the door is open and `+0.3 °C`
  otherwise, so the thermal feature family itself encodes the door event;
- the door state is generated directly by the same fixture, so A2b receives the
  generator's own state variable.

A2a already reaches OOF AP 0.999987 without any door feature. The A2b delta is
therefore consistent with a redundant encoding of the same synthetic event, not
with new physical early-warning value. A model that achieves AP near 1.0 here
has **not** proven early physical prediction; it has recognized how the fixture
was generated.

## 7. Effect direction and uncertainty

- Direction: A2b ≥ A2a in pooled OOF AP by 1.3e-05 (UNWEIGHTED) and 3.0e-05
  (weighted); per-fold AP is tied at 1.0000.
- Magnitude: effectively zero on a saturated synthetic control.
- Uncertainty: not estimable for the real plant; 8 correlated development pairs
  and 4 folds do not support a confidence interval or significance claim.
- No physical superiority, equivalence or actionable early-warning claim is
  made.

## 8. Exclusions and limitations

- 960 windows censored by the 60 s horizon crossing the fixture coverage;
  excluded, never negative.
- 0 untrusted-label exclusions.
- No electrical/actuation/environment feature entered either arm.
- The fixture is deterministic and does not approximate the six-litre plant.
- The locked test partition was not used.
- Door-context value on a real plant remains untested and not estimable with the
  current evidence.

## 9. Reproduction and binding

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
| Reference horizon | 60 s, `ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN` |
| Analysis code | `c415d74469e8e1a3fa0c693765a8c2f3a185562df382249fa8f959f367dfbe2c` |

## 10. Unresolved questions

- Does door context add predictive value on a real eligible population with a
  frozen target and horizon? **Not estimable; 0 eligible real runs.**
- Is the real MC-38 polarity/quality attested for the accepted S2 windows?
  **No; door quality/polarity attestation remains an A-owned gap.**
- Does the A2b door delta survive outside the synthetic generator? **Untested.**
