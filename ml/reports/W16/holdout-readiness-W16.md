# W16 Holdout Readiness, Integrity and Gate G4 Assessment (B-W16-01 / B-W16-03 / Gate G4)

> **Task:** B-W16-01 holdout integrity + B-W16-03 interpretation readiness +
> Appendix for Gate G4.
> **Pre-registration manifest:** `ml/reports/W16/locked-test-manifest-W16.json`
> **Manifest SHA-256:** `80442242dd5025f20a3f8b0d3ea9f757579830bddba8e0e04c8b394b693709e2`
> **Generation base:** `b9b93e10deeb5b9e2cfbdfba1bba0d17052ec4a4`
> **Holdout access:** `NOT_AUTHORIZED` · **Holdout opened:** no (no recorded
> opening in tracked metadata) · **Evaluation:** `NOT_RUN`

## 1. Prerequisite reconciliation (Phase A)

Status vocabulary: `PASS_VERIFIED`, `FAIL_VERIFIED`,
`BLOCKED_BY_MISSING_EVIDENCE`, `NOT_VERIFIED`, `NOT_APPLICABLE`.

| Prerequisite | Observed evidence | Source (revision / hash) | Status | W16 implication |
|---|---|---|---|---|
| Physical dataset with immutable source hashes | No real dataset; one candidate capture, 0 eligible | `ml/reports/W08/gate-b-manifest-W08.json` (`1dde8ea3…`) | BLOCKED_BY_MISSING_EVIDENCE | Cannot define a final test population |
| Gate B physical data | `RED`, 12 reason codes | W08 manifest | FAIL_VERIFIED | Blocks any predictive claim |
| Predictive-eligible real runs | `0` | W13 `reconciliation` (`02a76660…`) | FAIL_VERIFIED | No population to split or evaluate |
| Grouped real benchmark | `NOT_ESTABLISHED` | W12 (`ef06f971…`) | BLOCKED_BY_MISSING_EVIDENCE | No real benchmark exists |
| Gate G3 | `NO-GO / FIX DATA` | W12 `scientific_verdicts` | FAIL_VERIFIED | Stays RED until A/data gates close |
| Primary horizon | `NOT_FROZEN`, `primary_horizon_s = null`; 60/120/300 s provisional | W13 `decision` | BLOCKED_BY_MISSING_EVIDENCE | §92 freeze unmet |
| Critical target / representative temperature | `DEVELOPMENT_CANDIDATE_NOT_FROZEN` / `NOT_SELECTED` | `ml/xgb-v1-config.yaml` | BLOCKED_BY_MISSING_EVIDENCE | Label definition cannot be final |
| Operating threshold | `0.5`, `ILLUSTRATIVE_NOT_FROZEN` | `model-manifest-W15.json` (`85960c82…`) | BLOCKED_BY_MISSING_EVIDENCE | No valid warning rule |
| Warning persistence | `NOT_FROZEN`, no `k` | model manifest | BLOCKED_BY_MISSING_EVIDENCE | No valid warning rule |
| Calibration semantics | `RISK_SCORE_ONLY`, no fit, no probability claim | W14 `calibration-report.md`; W14 manifest (`e4a0263e…`) | PASS_VERIFIED (score-only consistency) | Legal score-only mode; no probability wording |
| Real EWT | `NOT_ESTIMABLE` (`EWT_UNAVAILABLE_NO_QUALIFIED_COMMON_TRAJECTORY`) | W14 `AIW-report.md` | BLOCKED_BY_MISSING_EVIDENCE | No lead-time evidence |
| Real AIW | `NOT_ESTIMABLE` (`AIW_UNAVAILABLE_MEASURED_LATENCY_CHAIN_MISSING`) | W14 `AIW-report.md` | BLOCKED_BY_MISSING_EVIDENCE | No actionability evidence |
| W15 model artifact | `25a8ef7a…`, `SYNTHETIC_SOFTWARE_CONTROL_ONLY`, `NON_DEPLOYABLE_CANDIDATE` | `model-manifest-W15.json` | FAIL_VERIFIED for release use | Not a release candidate |
| W15 model candidate config | `coldguard-xgb-v1-development-v1` (`4369f39f…`), `DEVELOPMENT_CONFIG_CANDIDATE` | `hyperparameter-freeze-candidate-W15.json` (`07d6b6d1…`) | NOT_VERIFIED for release | Hyperparameters not scientifically selected |
| Feature registry | `CG-FEAT-1.0`, `FROZEN_DEFINITIONS`, schema `1d36d338…` | `ml/feature-registry-v1.yaml` | PASS_VERIFIED (definitions only) | Frozen definitions ≠ approved model |
| Holdout isolation metadata | 4 test runs / 2 pairs disjoint from 16 development runs; no test usage flags | W11 manifest (`855c5beb…`); fold manifest; W13/W14/W15 populations | PASS_VERIFIED (declared metadata only) | See §2 |
| Prior holdout access history | No opening recorded anywhere in tracked metadata | W11–W15 manifests | PASS_VERIFIED with limitation | See §2.3 |
| Required approvals (B/A/D/C/lead) | None issued | `approval-ledger-W16.json` absent | BLOCKED_BY_MISSING_EVIDENCE | Gate cannot pass |

## 2. Holdout integrity evidence (B-W16-01, metadata only)

### 2.1 Known identities

| Item | Value |
|---|---|
| Synthetic dataset | `W11_EXPANDED_SYNTHETIC_GROUPED` (`coldguard-w11-synthetic-grouped-v1`) |
| Independent groups | 10 pairs (`W11-PAIR-001…010`), one effective group per pair |
| Development runs | 16 (8 train, 8 validation) |
| Locked-test runs (synthetic) | `CG-W11-S1-001`, `CG-W11-S1-002`, `CG-W11-S2-001`, `CG-W11-S2-002` |
| Locked-test pairs | `W11-PAIR-001`, `W11-PAIR-002` |
| Split seed | `42` |
| Physical dataset ID | **none** |

These identities are synthetic fixture metadata. No feature values, labels,
predictions or outcomes for the test runs were read, computed or written by this
milestone. The W11 fixture is generated in memory by the existing test harness;
no locked-test payload file exists in the repository.

### 2.2 Disjointness proof (declared metadata)

Verified by `W16-DS-05…DS-08` in the manifest:

- `test_runs ∩ (train_runs ∪ validation_runs) = ∅`;
- no `pair_id` appears in more than one partition;
- the W11 split, W11 fold manifest, W13 split identity, W14 population and W15
  population all declare the identical 4-run test set;
- the registered test set equals the observed test set;
- 4 test runs are unique; 16 development runs are unique;
- no per-run physical source hash exists, so physical duplicate-lineage audit is
  `BLOCKED_BY_MISSING_EVIDENCE` (not assumed clean).

### 2.3 Prior-access accounting and its limitation

`test_partition_used = false` (W11), `locked_test_used = false` (W11/W15),
`locked_test_untouched = true` (W13/W15) and `locked_test.opened_at = null`
everywhere. No evaluation receipt exists. The gate therefore records
`prior_access_status = NO_RECORDED_OPENING` and `holdout_opened = false`, with
an explicit limitation: tracked metadata cannot prove the absence of
out-of-band access that left no repository record. This is an accounting
statement, not an absolute proof of non-access.

### 2.4 Isolation audit (recorded, not re-derived)

The never-used-for ledger (feature selection, architecture selection,
hyperparameter tuning, class-weight/sampling, calibration fitting, threshold
selection, persistence selection, primary-horizon selection, ablation-based
winner selection) is recorded in the manifest as
`NO_RECORDED_TEST_EXPOSURE` with audit basis
`DECLARED_REPORT_METADATA_ONLY`. The W15 model card additionally documents the
synthetic door-time shortcut, which is itself a reason the artifact cannot be
promoted.

## 3. Fail-closed gate and no-access proof (summary)

Implemented in `ml/src/coldguard_ml/w16_readiness.py` (stdlib only) and
`ml/scripts/w16-preflight-W16.py`. The executable proofs live in
`ml/tests/test_w16_readiness.py` (83 adversarial cases) and
`ml/tests/test_w16_delivery.py`:

- static: the module imports only Python standard-library modules; it defines no
  evaluator/predict/fit entry point; it contains no `open`, `read_text`,
  write, subprocess or dynamic-import call;
- static: the driver imports only argparse/hashlib/json/subprocess/sys/pathlib/
  typing/yaml plus `load_registry`, `load_benchmark_config` and the gate module;
  it references no benchmark/evaluation function; no `--force`, `--unlock` or
  `--ignore-gates` option exists;
- runtime: with instrumented `Path.read_text`/`Path.read_bytes`/`builtins.open`,
  a full preflight reads only declared metadata and model artifacts; decoy
  `locked-test-observations`/`holdout-*` files are never touched;
- runtime: artifact records with forbidden roles or paths are refused before any
  read, and the gate writes no files at all;
- determinism: two runs over the same metadata are byte-identical, and a rerun
  against the committed manifest changes nothing.

## 4. Gate G4 assessment (Phase I)

Doc `04` §31: G4 requires locked predictive evidence, positive or honestly
interpretable AIW, shadow-capable inference, security baseline, `SAFE_LOCAL`,
reconnect and command physical verification. A positive model result alone is
insufficient.

```text
G4_READY = false
SCIENTIFIC_PRECEDENCE: Gate B / G3 remain RED
```

| G4 prerequisite | Owner | Verified state | Status |
|---|---|---|---|
| Locked predictive evidence | B | Evaluation `NOT_EXECUTED_PREREQUISITES_UNMET`; no AP/EWT/AIW | NOT_READY |
| Positive or honestly interpretable AIW | B (with A/C/D inputs) | `AIW = NOT_ESTIMABLE`; no measured latency chain; D W13 calculator has no measured inputs | NOT_READY |
| Shadow-capable inference | C | W15/W16 inference code exists only on unmerged C branches; A W17 reports zero synchronized shadow runs (`DATA_INSUFFICIENT`) | NOT_READY |
| Security baseline | D | D W01 design only; broker auth/ACL merged; TLS only on unmerged C branch; no D signoff | NOT_READY |
| `SAFE_LOCAL` | D/A | D policy and exit gate unit-tested; A W08 `NOT DEMONSTRATED`; no broker-loss physical trace | NOT_READY (physical) |
| Reconnect / outage resynchronization | C | C-W16 code/tests unmerged; no physical broker-loss evidence | NOT_READY |
| Command physical verification | A | A-W06-05 `BLOCKED`; W21 PASS is on-device software injection with output stage compiled out | NOT_READY |
| Plant/dataset stability | A | W16 freeze `BLOCKED`; 0 certified S1, 0 valid S2 | NOT_READY |

**Member B may document this recommendation; B cannot grant team release
approval. No synthetic metric may override Gate B/G3 RED.** Even if the W16
preflight were fully green on B-side evidence, G4 must remain blocked until every
team-owned prerequisite above is independently verified.

## 5. Outstanding work and resume gates

| Task | State | Exact gate to resume |
|---|---|---|
| B-W16-01 holdout integrity | VERIFIED_METADATA_ONLY | Replace the synthetic membership with a frozen physical split once Gate B produces ≥3 evidence-grade runs per partition |
| B-W16-02 locked evaluation | NOT_EXECUTED_PREREQUISITES_UNMET | All 45 gate requirements PASS, including 5 approvals and release authorization; then a separate operator-authorized one-time run per `locked-test-protocol-W16.md` |
| B-W16-03 interpretation | NO_INTERPRETATION_TEST_NOT_RUN | Requires a completed evaluation receipt; criteria pre-registered in the protocol |
| B-W16-04 model RC | NOT_ISSUED / BLOCKED | Requires B-W16-02 and team-lead release authorization |
| Gate G4 | NOT_READY | All seven team-owned prerequisites verified; B contributes only its evidence |

## 6. Limitations

- Metadata-level audit only; no physical validation was performed in W16.
- The synthetic W11 holdout cannot substitute for physical evidence; its
  membership was inspected as metadata, its payload was not opened.
- The absence of recorded holdout access does not prove absence of out-of-band
  access.
- Hash verification covers the declared model/config/registry identities, not
  future physical data quality.
