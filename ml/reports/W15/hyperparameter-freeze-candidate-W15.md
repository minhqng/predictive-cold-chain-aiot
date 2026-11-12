# W15 — hyperparameter freeze candidate

**Task:** B-W15-03 · **Status: `DEVELOPMENT_CONFIG_CANDIDATE`.**

This record stops broad exploratory tuning and declares a reproducible development
configuration. It is **not** `PHYSICALLY_VALIDATED_MODEL`, **not**
`APPROVED_RELEASE_MODEL` and **not** `W16_LOCKED_TEST_READY`.

Machine-readable companion: `hyperparameter-freeze-candidate-W15.json`
(SHA-256 `07d6b6d1efe119e9b33937c44850486382ec5b89adb0008b093bbe380b4a0aa6`).

## 1. Model identity

| Field | Value |
|---|---|
| Model family | XGBoost |
| Library version | 3.4.1 |
| Config version | `coldguard-xgb-v1-development-v1` |
| Config status | `DEVELOPMENT_CANDIDATE_NOT_SCIENTIFICALLY_SELECTED` |
| Config SHA-256 (canonical parsed config) | `4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a7660dd6481ee1f71a84` |
| Feature version | `CG-FEAT-1.0` |
| Feature schema SHA-256 | `1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9` |
| Output semantics | `risk_score` (not a probability) |
| Calibration status | `RISK_SCORE_ONLY` |

## 2. Parameters (actual repository values)

| Parameter | Value | Source |
|---|---:|---|
| `objective` | `binary:logistic` | pre-existing W11 config |
| `tree_method` | `hist` | pre-existing W11 config |
| `max_depth` | 3 | pre-existing W11 config |
| `learning_rate` | 0.05 | pre-existing W11 config |
| `n_estimators` | 60 | pre-existing W11 config |
| `subsample` | 1.0 | pre-existing W11 config |
| `colsample_bytree` | 1.0 | pre-existing W11 config |
| `reg_lambda` | 1.0 | pre-existing W11 config |
| `reg_alpha` | 0.0 | pre-existing W11 config |
| `random_state` | 42 | pre-existing W11 config |
| `n_jobs` | 1 | pre-existing W11 config (deterministic fit) |
| `scale_pos_weight` | 1.0 for the artifact | `UNWEIGHTED` artifact strategy |
| Risk threshold | 0.5 | pre-existing illustrative W11 threshold, **not frozen** |

The `TRAIN_FOLD_CLASS_WEIGHT` strategy remains a predeclared comparison arm; it is
not the artifact strategy. No parameter was selected by looking at the W16 locked
test. Non-model fit flags: `verbosity=0` (silent fit); `n_jobs=1` is the config
value. Neither changes the model family or the parameters above.

## 3. Freeze scope

Frozen as a development candidate:

- XGBoost family and parameter values above;
- ordered A3b feature identity (28 ids, frozen W11 order);
- `CG-FEAT-1.0` schema hash;
- label spec version `coldguard-w11-development-label-v1`;
- development fixture, split seed 42 and 4 grouped folds;
- output semantics `risk_score`;
- artifact strategy `UNWEIGHTED`.

Explicitly **not** frozen:

- primary physical horizon (W13 remains `NOT_FROZEN`);
- critical target / representative temperature;
- operating threshold (0.5 is illustrative);
- warning persistence;
- calibration model;
- W16 locked-test result;
- physical model release eligibility.

## 4. Parameter-choice provenance

All model parameters except the artifact's class weight are inherited from the
pre-existing W11 configuration. The artifact's `scale_pos_weight = 1.0` is the
predeclared `UNWEIGHTED` strategy, not a W11 config value and not a tuned parameter.
W15 performed no hyperparameter search, no model contest and no
threshold/persistence selection. The parameters were not optimized on real physical
data and are not claimed to be physically selected.

If a future week changes a parameter, it must document why the current candidate is
defective and prove the change used no locked-test information.

## 5. Development identity

| Item | Value |
|---|---|
| Dataset | `W11_EXPANDED_SYNTHETIC_GROUPED` |
| Fixture version | `coldguard-w11-synthetic-grouped-v1` |
| Development runs | 16 (8 S2 + 8 S1) |
| Independent pair groups | 8 |
| Locked test runs | `CG-W11-S1-001`, `CG-W11-S1-002`, `CG-W11-S2-001`, `CG-W11-S2-002` |
| Grouped CV | 4 folds, seed 42 |
| Evaluable windows | 1936 (480 positive / 1456 negative) |
| Reference horizon | 60 s, `ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN` |

## 6. Binding

- W15 manifest SHA-256: `3f1a16939e1c16345e9948eb109085d123d3e57a57717132b0ab9c2d89d5eafa`
- Artifact: `model/model.ubj`, SHA-256 `25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f`
- Artifact manifest: `model/model-manifest-W15.json`, SHA-256 `85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e`

## 7. Limitations

- The candidate is a software configuration on a deterministic synthetic fixture.
- Eight synthetic pair groups do not support a physical model acceptance decision.
- The saturated A3 result provides no discriminative evidence for parameter choice.
- The candidate is not calibrated, not threshold-frozen and not persistence-frozen.
