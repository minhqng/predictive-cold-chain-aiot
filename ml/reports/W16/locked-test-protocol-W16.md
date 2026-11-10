# W16 One-Time Evaluation Protocol and Analysis Registration (B-W16-02/B-W16-03 preparation)

> **Status:** protocol prepared, **not executed**. This document defines the exact
> procedure a later, separately authorized W16 evaluation must follow.
> **Pre-registration manifest:** `ml/reports/W16/locked-test-manifest-W16.json`
> **Manifest SHA-256:** `80442242dd5025f20a3f8b0d3ea9f757579830bddba8e0e04c8b394b693709e2`

## 1. Scope and authority boundary

This protocol is a pre-declaration, not an evaluation. It exists so that a future
one-time locked test cannot be tuned, reinterpreted or quietly repeated after its
outcome is known (Doc `03` §§92-93, §133). Nothing here authorizes opening the
holdout: the holdout remains `NOT_AUTHORIZED` and `holdout_opened = false`.

A preflight `PASS` means only that the metadata contract is complete. The actual
one-time evaluation requires a separate explicit operator decision after external
acceptance of this pre-registration.

## 2. Required sequence (Doc `03` §92; Doc `05B` §44)

```text
valid physical dataset
→ frozen run/test identities
→ accepted grouped split
→ final model/feature/target/horizon freeze
→ frozen operating threshold and persistence
→ calibration semantics confirmed
→ documented release approval
→ preflight PASS
→ one authorized locked evaluation
→ immutable result receipt
→ interpretation without retuning
```

No step may be skipped, reordered or executed speculatively. Steps 1–8 are the
gate implemented in `coldguard_ml.w16_readiness`; steps 9–11 belong to the
future authorized operation and are **not implemented in this PR**. The current
driver enumerates only the existing W08/W11–W15 metadata: a future physical
dataset, frozen split and threshold-freeze record must be added to the driver's
declared inputs (the gate API already accepts them) before a physical preflight
can pass.

## 3. Required inputs for the future operation

| Input | Identity requirement |
|---|---|
| Dataset | physical dataset ID with immutable source/manifest hashes; run and pair IDs |
| Split | frozen `test_runs`, pair lineage, `locked_test.frozen_at`, `opened_at = null` |
| Model | native artifact SHA-256, model/config hashes, feature schema + ordered IDs |
| Label | frozen target definition: boundary, representative temperature, horizon |
| Operating rule | frozen threshold value and warning persistence `k`; the threshold must carry a committed selection record (`reports/W16/threshold-freeze-W16.json`) binding the threshold value, model artifact hash, analysis code hash and an evidence SHA-256 — the source is never inferred from a status string |
| Calibration | frozen calibration method or risk-score-only semantics |
| Code | analysis code SHA-256 (pre-registered at manifest generation; covers the gate plus the registered metric/feature modules) |
| Approvals | B method, A physical, D policy, C telemetry, team-lead release authorization |
| Environment | Python 3.12 + `ml/uv.lock` package versions |

## 4. Required outputs of the future operation

| Output | Content |
|---|---|
| Evaluation receipt | immutable JSON: evaluation ID, population identity, all input hashes, model/policy versions, command record, success/failure status |
| Result report | per-metric values with denominators, per-run and pooled, exclusions and censoring counts |
| Non-estimable ledger | every metric that is undefined, with its exact reason code |
| Interpretation record | exactly one of the three pre-registered categories, or a documented non-applicability |
| Disposition record | model RC issued or refused, with its evidence |

### 4.1 Immutable evaluation receipt schema (minimum)

```json
{
  "evaluation_id": "CG-EVAL-W16-001",
  "evaluated_at": "<UTC>",
  "operator_authorization_id": "<approved authorization record id>",
  "preregistration_manifest_sha256": "<64-hex>",
  "holdout": {
    "dataset_id": "<physical dataset id>",
    "test_run_ids": ["..."],
    "test_pair_ids": ["..."],
    "population_identity_sha256": "<64-hex>"
  },
  "inputs": {
    "model_artifact_sha256": "<64-hex>",
    "model_config_sha256": "<64-hex>",
    "feature_schema_hash": "<64-hex>",
    "analysis_code_sha256": "<64-hex>",
    "label_identity": {"horizon_s": 0.0, "boundary_c": 0.0, "spec_version": "..."},
    "operating_threshold": 0.0,
    "warning_persistence_k": 0,
    "calibration_semantics": "risk_score | calibrated_probability",
    "environment": {"python": "3.12", "lockfile_sha256": "<64-hex>"}
  },
  "execution": {
    "status": "SUCCESS | FAILED | ABORTED",
    "command": "<exact command>",
    "started_at": "<UTC>",
    "finished_at": "<UTC>",
    "failure_reason": null
  },
  "outputs": {"result_report_sha256": "<64-hex>"}
}
```

## 5. Once-only integrity rules

1. The receipt is created before the first observation is read and completed
   after the run; a successful evaluation cannot exist without a receipt.
2. A receipt binds the exact holdout population and every artifact hash used.
3. `SUCCESS`, `FAILED` and `ABORTED` are distinct; an attempted-but-failed run is
   still an opening and must be recorded.
4. Any earlier opening must be preserved in the receipt history; a later run is a
   **repeat**, not a first evaluation.
5. Re-running with any changed input (model, threshold, persistence, horizon,
   feature set, analysis code) is a new evaluation and requires a new, independent
   test population (Doc `03` §93).
6. Post-test model selection under a false first-test claim is prohibited; the
   receipt chain makes it detectable.

## 6. Post-test defect rule (Doc `03` §93)

If the final test exposes a defect that requires a model or code revision:

- the test is **no longer untouched**;
- subsequent analyses must be disclosed as exploratory post-test revisions;
- fresh final claims require a **new independent test population**.

Bug fixing after exposure is not permission to reuse the same test indefinitely.

## 7. Statistical analysis registration (Phase F)

No metric value is present in this registration; values exist only after the
authorized one-time run. Implementations reuse the existing W03/W12 code; no
second metric engine is introduced. The registered analysis-code hash covers
the preflight gate and the metric/feature implementation modules
(`grouped_evaluation`, `event_evaluator`, `evaluation_contract`,
`w14_calibration`, `feature_pipeline`, `feature_registry`, `labels`,
`splitting`).

### 7.1 Primary metric

| Field | Definition |
|---|---|
| Metric | Non-interpolated average precision (`average_precision_score`) |
| Canonical constant | `PRIMARY_PREDICTIVE_METRIC` (`coldguard_ml.evaluation_contract`) |
| Implementation | `coldguard_ml.grouped_evaluation.classification_metrics` |
| Data source | Frozen locked-test anchors from the registered test runs only |
| Population | Eligible, trusted anchors; exclusions per §7.6 |
| Unit | Dimensionless, `[0, 1]` |
| Denominator | All eligible positives and negatives; AP averages precision at each positive rank |
| Undefined cases | Single-class test population; zero eligible anchors; label unavailable for any test run |
| Undefined behavior | `UNDEFINED_SINGLE_CLASS_TEST` / `UNDEFINED_NO_ELIGIBLE_ANCHORS` — never `0` or `1` |
| Interpretation boundary | Discrimination on this prototype/configuration only; not a probability, not a deployment claim |

### 7.2 Supporting sample metrics

| Metric | Rule | Denominator | Undefined behavior |
|---|---|---|---|
| Precision | `tp / (tp + fp)` at frozen threshold + persistence | predicted-positive anchors | `NO_PREDICTED_POSITIVES` |
| Recall | `tp / (tp + fn)` at frozen threshold + persistence | eligible positive anchors | `UNDEFINED_NO_POSITIVES` |

### 7.3 Event metrics

| Metric | Rule | Denominator |
|---|---|---|
| Warning episode | Risk above frozen threshold for at least the frozen persistence `k`, bridging only per the frozen matching policy | — |
| False-warning burden | `false_warning_episodes_per_eligible_hour` | Trusted eligible run-hours in the locked test |
| Missed critical events | Count of eligible critical events without a matched warning | Eligible critical events |

Event evaluation reuses `coldguard_ml.event_evaluator.evaluate_events`; episode,
association and chatter policies must be frozen first.

### 7.4 EWT

`EWT = t_reactive − t_predictive` in seconds, where `t_predictive` is the first
valid persistent predictive warning and `t_reactive` the first reactive criterion
time. Negative values are kept. Preconditions: qualified common trajectory,
trusted event time, no intervening predictive intervention, uncensored reactive
crossing, frozen reactive criterion. Any missing precondition →
`NOT_ESTIMABLE` with the exact reason, never `0`. Implementation:
`coldguard_ml.evaluation_contract.compute_ewt`.

### 7.5 AIW

`AIW = t_critical − t_warning − T_system − T_physical` in seconds. `T_system` is
sensing + inference + policy + command overhead from the measured latency chain.
Preconditions: measured command-to-effect latency chain, frozen critical
criterion, trusted warning time. Missing → `NOT_ESTIMABLE`, never `0`.
Implementation: `coldguard_ml.evaluation_contract.compute_aiw`.

### 7.6 Calibration

- If the frozen semantics are `risk_score`: calibration metrics are
  `NOT_APPLICABLE` and probability or percentage wording is prohibited
  (Doc `03` §59).
- If the frozen semantics are calibrated probability: fit on development data
  only; the locked test is never used for calibration (Doc `03` §60); report
  Brier/reliability diagnostics with bin counts.

### 7.7 Aggregation and independence

- Independent unit is the run; pair lineage collapses paired runs into one group.
- Report per independent test run/group and pooled across groups.
- Correlated windows and correlated folds are **never** counted as independent
  experiments (W15 lesson: 4 grouped folds ≠ 4 physical experiments).

### 7.8 Invalid, censored and missing data

Exclude only per predeclared validity rules; report exclusion counts, censored
counts and run/group denominators. Never impute and never zero-fill missingness
(registry policy `explicit_missing_never_zero_filled`).

### 7.9 Uncertainty and limitations

Report independent run/group counts, class and event denominators, exclusion
counts with reasons, explicit non-estimable statuses, and a limitations section
stating that results apply only to the tested prototype/configuration.

## 8. Interpretation contract (Phase G)

Pre-registered categories (Doc `05B` §44; W03 methodology):

```text
SUPPORTS_PREDICTIVE_USEFULNESS
MIXED_EVIDENCE
DOES_NOT_SUPPORT
```

Before the test, the interpretation rules are fixed:

| Evidence pattern (after validity exclusions) | Category |
|---|---|
| AP meaningfully above the pre-declared development baseline; event recall acceptable; false-warning burden bounded; EWT/AIW at least estimable with a positive or honestly interpretable AIW | SUPPORTS_PREDICTIVE_USEFULNESS |
| Discrimination present but event burden, missed events, lead time or actionability unresolved/estimable-negative | MIXED_EVIDENCE |
| Discrimination at or below the pre-declared baseline, or event behavior uninterpretable | DOES_NOT_SUPPORT |
| Any metric undefined | reported as non-estimable; does not count as zero and may not be selected into the best category |
| Test not run | `NO_INTERPRETATION_TEST_NOT_RUN` |

Additional required criteria: discrimination, event-level warning burden, missed
events, lead time, measured actionability, practical relevance, uncertainty,
limitations, and explicit failure/non-estimability handling. The category is
assigned by these rules, never chosen retrospectively. No retuning is permitted
after reading the result (Doc `03` §93; Doc `05B` §44).

## 9. Prohibited operations

- Opening the holdout in this milestone or any unapproved future execution.
- Computing any locked-test predictive metric outside the authorized operation.
- Tuning model, threshold, persistence, horizon, calibration or features on test
  data at any point.
- Treating a failed/aborted attempt as if no opening occurred.
- Reporting `0` for an unobservable AP, EWT or AIW.
- Issuing a model release candidate without the full gate and receipt.
- Using this protocol or a preflight `PASS` as a Gate G4 approval.
- Fabricating approval, threshold-freeze or physical-evidence records. The gate
  validates structure, hashes and binding identities; it cannot authenticate the
  human authority behind a record. Approvals remain a human process control.

## 10. Current status

```text
B-W16-02: NOT_EXECUTED_PREREQUISITES_UNMET
B-W16-03: NO_INTERPRETATION_TEST_NOT_RUN
B-W16-04: NOT_ISSUED / BLOCKED
HOLDOUT OPENED: NO (no recorded opening in tracked metadata)
```
