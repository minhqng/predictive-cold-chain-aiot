# W16 Locked-Test Result — Refusal Report (B-W16-02)

> **Task:** B-W16-02 — Evaluate the locked predictive test once (Doc `05B` §44).
> **Status:** `NOT_EXECUTED_PREREQUISITES_UNMET`
> **Interpretation:** `NO_INTERPRETATION_TEST_NOT_RUN`
> **Pre-registration manifest:** `ml/reports/W16/locked-test-manifest-W16.json`
> **Manifest SHA-256:** `80442242dd5025f20a3f8b0d3ea9f757579830bddba8e0e04c8b394b693709e2`
> **Generation base:** `b9b93e10deeb5b9e2cfbdfba1bba0d17052ec4a4` (W15 remote head)
> **Header:** `PRE_REGISTRATION_ONLY` · `holdout_access = NOT_AUTHORIZED` ·
> `holdout_opened = false` · `evaluation_status = NOT_RUN`

## 1. Result

**Evaluation NOT_RUN. No AP, precision, recall, false-warning burden, missed-event
count, EWT, AIW or calibration metric exists, and no physical predictive verdict is
made.** The locked predictive holdout remains unopened. The three canonical
interpretation categories (`SUPPORTS_PREDICTIVE_USEFULNESS`, `MIXED_EVIDENCE`,
`DOES_NOT_SUPPORT`) require a completed evaluation and are therefore unavailable;
the only valid W16 interpretation record is:

```text
NO_INTERPRETATION_TEST_NOT_RUN
```

This is not a failure of the model. It is a refusal to run a final test whose
scientific preconditions do not exist. Doc `03` §92 requires the model, feature
version, hyperparameters, artifact hash, threshold, persistence, calibration method
and primary horizon to be frozen before the locked test is opened; none of the
scientific freeze items is in force.

## 2. Unmet-gate ledger

Every line is produced deterministically by
`coldguard_ml.w16_readiness.evaluate_w16_readiness()` and recorded in
`readiness_decision.refused_requirements` of the manifest.

| Reason code | Unmet requirement | Canonical clause |
|---|---|---|
| `PHYSICAL_DATASET_IDENTITY_MISSING` | No authoritative physical dataset with immutable source hashes exists (`0` predictive-eligible runs). | Doc `01` §17; Doc `03` §137 Gate B |
| `DATASET_EVIDENCE_CLASS_NOT_PHYSICAL` | Registered dataset class is `SYNTHETIC_SOFTWARE_CONTROL_ONLY`; a synthetic control cannot substitute for physical evidence. | Doc `03` §103, §137 |
| `TEST_MEMBERSHIP_NOT_FROZEN` | `locked_test.frozen_at` is null; no frozen final test membership exists. | Doc `03` §47, §49, §92 |
| `RUN_SOURCE_IDENTITY_MISSING` | No per-run physical source hashes; duplicate-source lineage cannot be audited. | Doc `05B` §8 |
| `PHYSICAL_RUN_VALIDITY_MISSING` | Gate B reports `RED`; the one candidate capture is not an evidence-grade run. | Doc `01` §17, §33; Doc `03` §137 |
| `HARDWARE_CONFIG_NOT_VERIFIED` | Hardware `CG-HW-001` is `DECLARED_NOT_VERIFIED`. | Doc `01` §39.1 |
| `TIME_PROVENANCE_INADEQUATE` | Time domain is `BOOT_SCOPED_UPTIME`; clock synchronization is `NOT_EVIDENCED`. | Doc `01` §18 |
| `SAMPLE_QUALITY_UNTRUSTED` | Completeness checks are `NOT_EVALUABLE` (no declared capture duration). | Doc `01` §33; W08 completeness policy |
| `CALIBRATION_PROVENANCE_MISSING` | Measurement calibration is `NOT_AVAILABLE`. | Doc `01` §39.2; Doc `03` §137 |
| `MODEL_SYNTHETIC_NON_DEPLOYABLE` | Registered model is `SYNTHETIC_SOFTWARE_CONTROL_ONLY` / `NON_DEPLOYABLE_CANDIDATE`. | Doc `03` §103, §137; Doc `05B` §44 |
| `CRITICAL_TARGET_UNFROZEN` | Target status is `DEVELOPMENT_CANDIDATE_NOT_FROZEN`; `boundary_c` is null. | Doc `03` §42-43, §92 |
| `REPRESENTATIVE_TEMPERATURE_UNFROZEN` | Representative temperature is `DEVELOPMENT_CANDIDATE_NOT_SELECTED`. | Doc `03` §42-43 |
| `PRIMARY_HORIZON_UNFROZEN` | W13 decision is `NOT_FROZEN` with `primary_horizon_s = null`; the 60 s value is an engineering reference only. | Doc `03` §44, §84, §92 |
| `OPERATING_THRESHOLD_UNFROZEN` | Threshold `0.5` is `ILLUSTRATIVE_NOT_FROZEN`, not selected on development data. | Doc `03` §87, §92 |
| `WARNING_PERSISTENCE_UNFROZEN` | Persistence `k` is `NOT_FROZEN` and no value is recorded. | Doc `03` §88, §92 |
| `EVENT_MATCHING_POLICY_UNFROZEN` | Episode/association policy is `SYNTHETIC_ILLUSTRATIVE`. | Doc `03` §89-90 |
| `APPROVAL_MISSING:B_METHOD` | Member B methodological freeze approval has not been issued. | Doc `05B` §44 |
| `APPROVAL_MISSING:A_PHYSICAL` | Member A physical-measurement authorization has not been issued. | Doc `01` §17-18 |
| `APPROVAL_MISSING:D_POLICY` | Member D critical-target/threshold/persistence authorization has not been issued. | Doc `03` §42, §87-88 |
| `APPROVAL_MISSING:C_TELEMETRY` | Member C telemetry time-provenance support has not been issued. | Doc `01` §18 |
| `APPROVAL_MISSING:TEAM_LEAD` | Team-lead freeze approval has not been issued. | Doc `04` §31 |
| `RELEASE_AUTHORIZATION_MISSING` | No record authorizes a one-time locked evaluation. | Doc `03` §92-93 |
| `SCIENTIFIC_PREREQUISITES_BLOCKED` | Gate B `RED`, Gate G3 `NO-GO / FIX DATA`, `0` predictive-eligible real runs. | Doc `03` §137; Doc `04` §31 |
| `FREEZE_LEDGER_INCOMPLETE` | The complete freeze ledger contains non-`FROZEN_APPROVED` fields (model identity, training dataset, target, representative temperature, horizon, threshold, persistence, event matching, physical dataset, hardware, time provenance, run identity, calibration provenance). | Doc `03` §92; Doc `05B` §44 |

The full per-requirement ledger (47 requirements: 23 `PASS_VERIFIED`,
10 `FAIL_VERIFIED`, 14 `BLOCKED_BY_MISSING_EVIDENCE`) is in
`readiness_decision` and `requirements` of the manifest.

## 3. What was verified — and what it does not mean

These checks passed and are recorded in the manifest:

- the synthetic W11 test membership is internally consistent across the W11
  split manifest, the W11 fold manifest, the W13 split identity and the W14/W15
  populations (4 runs, 2 pairs), and is disjoint from the 16 development runs;
- no pair lineage crosses a partition in the declared metadata;
- `test_partition_used = false` and `locked_test_used = false` across W11–W15;
- the W15 native model bytes re-hash to
  `25a8ef7a71817d4d45a2d9bc3b4d6889c2dbf576c4da514d59fab1f6fc263f7f`;
- the model configuration hash (`4369f39f…`), feature schema hash
  (`1d36d338…`) and ordered-feature hash (`98491993…`) match their registered
  identities;
- the pre-registration and analysis code are frozen by SHA-256 in the manifest;
- the gate has no path to holdout observations (see `holdout-readiness-W16.md`).

Passing these checks means only that the *metadata contract is coherent*. It is
not predictive evidence, not calibration evidence, and not a Gate G4 approval.

## 4. Prohibited inferences

- `0` is not the value of AP, EWT, AIW, false-warning burden or missed events.
  Those quantities are unobserved and unobservable under the current gates.
- The W15 synthetic AP of `1.0` is a software control on a deterministic
  fixture; it is not a predictive result and is not carried into this record.
- A successful preflight, deterministic serialization, software parity or the
  absence of errors cannot substitute for a locked-test evaluation (Doc `03`
  §137; Doc `05B` §44).
- No post-hoc revision may be reported as a first test: if a later authorized
  run finds a defect and changes the model or code, the old test is no longer
  untouched (Doc `03` §93).

## 5. Reproduction

```bash
cd ml
uv lock --check
uv sync --locked --python 3.12 --extra test
uv run --locked --python 3.12 --extra test pytest -q
uv run --locked --python 3.12 --extra test python scripts/w16-preflight-W16.py \
  --out reports/W16
```

The preflight is deterministic: two runs over the same metadata produce
byte-identical manifests, and a rerun against the committed manifest changes
nothing. The manifest records the generation base revision
(`GENERATION_BASE_NOT_DELIVERY_COMMIT`); to reproduce it byte-for-byte after the
W16 commit, pass `--repository-revision <recorded generation base>` explicitly.
