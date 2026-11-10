# W18 no-online-tuning and freeze-drift audit

Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17 and Member A files), SYNTHETIC_SOFTWARE_FIXTURE (W17 replay and TEST_ONLY fixture), DERIVED_SOFTWARE_ASSERTION (monitor/trace/freeze/readiness results), EXTERNAL_DEPENDENCY (A/C/D interface snapshots), NOT_VERIFIED (absent live/physical evidence).
Canonical rule: do not adjust the model or threshold after each physical run.
This audit is read-only and implements no tuner, updater, retrainer,
recalibrator or threshold optimizer.

## Baseline distinction

Pinned baseline input: ml/reports/W18/freeze-baseline-W18.json (d1bcc8ff26ed28ed998fb2c43d7fa57ab928d6c4d90c1af801289016dd446581).
- Development baseline: DEVELOPMENT_BASELINE_UNCHANGED.
- Approved release freeze: MISSING_FREEZE_RECORD.
- A stable development baseline is not an approved release freeze.

## Protected fields

| field | baseline value | observed | status |
|---|---|---|---|
| model_artifact_id | coldguard-w15-synthetic-xgb-candidate-v1 | coldguard-w15-synthetic-xgb-candidate-v1 | UNCHANGED |
| model_artifact_sha256 | 25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da5... | 25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da5... | UNCHANGED |
| model_config_sha256 | 4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a... | 4369f39f44a1d3b4c27ec6dee8c47a7dc1fdfd3c5416a... | UNCHANGED |
| feature_version | CG-FEAT-1.0 | CG-FEAT-1.0 | UNCHANGED |
| feature_schema_hash | 1d36d338f35dd448b8c680075fdbe26785384f418a4ef... | 1d36d338f35dd448b8c680075fdbe26785384f418a4ef... | UNCHANGED |
| ordered_feature_ids_sha256 | 98491993d95ba78292cc245d637a1832ebdfb80b1eb02... | 98491993d95ba78292cc245d637a1832ebdfb80b1eb02... | UNCHANGED |
| primary_horizon | {"config_horizon_s":60.0,"horizon_s":60.0,"ho... | {"config_horizon_s":60.0,"horizon_s":60.0,"ho... | UNCHANGED |
| critical_target | {"boundary_c":null,"config_target_status":"DE... | {"boundary_c":null,"config_target_status":"DE... | UNCHANGED |
| operating_threshold | {"config_value":0.5,"status":"ILLUSTRATIVE_NO... | {"config_value":0.5,"status":"ILLUSTRATIVE_NO... | UNCHANGED |
| warning_persistence | {"k":null,"status":"NOT_FROZEN"} | {"k":null,"status":"NOT_FROZEN"} | UNCHANGED |
| calibration_semantics | {"config_status":"NOT_PERFORMED","score_seman... | {"config_status":"NOT_PERFORMED","score_seman... | UNCHANGED |
| event_matching_policy | {"association_status":"SYNTHETIC_ILLUSTRATIVE... | {"association_status":"SYNTHETIC_ILLUSTRATIVE... | UNCHANGED |
| model_library_version | 3.4.1 | 3.4.1 | UNCHANGED |
| w15_model_manifest_sha256 | 85960c821b6286fd18b0d012de20ddd58912d9d1bb965... | 85960c821b6286fd18b0d012de20ddd58912d9d1bb965... | UNCHANGED |

## Native model binding

Model file matches declared SHA-256: true.
Observed SHA-256: 25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f.
Expected SHA-256: 25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f.

## Inputs observed

- W15 model manifest SHA-256: 85960c821b6286fd18b0d012de20ddd58912d9d1bb965c5b9191b9cf4653107e
- W16 locked-test manifest SHA-256: 6e7e7f23881785f76463344663e08f0cf626f5ee137aa1f98a99772e1a1fe165
- W17 manifest SHA-256: 8b2e92e7c70134e5ab0c6ac796c900b681bc7d66f79eddb48ecc939ddcc33532

## Change-control contract

A future legitimate change must provide:

- artifact_id
- model_artifact_sha256
- model_config_sha256
- feature_schema_hash
- ordered_feature_ids_sha256
- reason
- owner
- affected_evidence
- evaluation_implications
- review_gate

A change following locked-test exposure must declare a new independent
evaluation; the old locked test is no longer untouched for the new model.

## Forbidden behaviors covered by controls

- threshold changed after an observed trace
- persistence modified after observed warnings
- model bytes changed without an identity update
- model swapped while preserving old hash metadata
- feature order changed silently
- horizon changed after inspecting evaluation output
- calibration semantics changed from risk score to probability
- a post-test revision reusing the old locked-test acceptance
- a missing freeze record treated as a verified freeze

## Result

Drift detected: false.
No approved freeze record exists, so no software assertion converts the
development baseline into a release freeze.
