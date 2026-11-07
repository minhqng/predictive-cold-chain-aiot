# ColdGuard W08 — Gate B dataset readiness

Report schema: `coldguard-w08-gate-b-readiness-report-v1` · layer `coldguard-w08-gate-b-readiness-v1`

| Provenance | Value |
|---|---|
| Analysis code SHA-256 | `da443b88fb07b81c072fd1670d85a686c905c57d946bde7826132c5206502653` |
| Repository revision | `cb11c8693fbbcd5f19d5f04476cd2aa06bd283aa` |
| Generation command | `python scripts/gate-b-readiness-W08.py --source ../evidence/A/W09/exports/CG-S1-H8C-600S.json --a-run-index ../evidence/A/W09/s1-run-index.json --scenario S1 --out reports/W08 --min-runs 3 --baseline-window-s 120.0 --event-window-s 60.0 --recovery-horizon-s 900.0 --split-seed 0 --repository-revision cb11c8693fbbcd5f19d5f04476cd2aa06bd283aa` |
| A run index SHA-256 | `eb71d3f58004a25e60315b39ed88e33daa7e069a7a1fc3df391713cfce33b5af` |
| Completeness policy | `coldguard-w08-completeness-policy-draft-v1` |

## 1. Declared purpose

- Scenario: `S1`
- Purpose: S1 normal-baseline predictive dataset
- Event required: NO
- Absolute event-time claim: YES

## 2. Gate decisions

| Gate | Observed status | Severity | Reason codes |
|---|---|---|---|
| `W08_SOFTWARE_VERIFICATION` | **GREEN** | INFO | SOFTWARE_VALIDATION_COMPLETED |
| `GATE_B_PHYSICAL_DATA` | **RED** | BLOCKING | ABSOLUTE_TIME_NOT_EVIDENCED, AUTHORITY_A_LEDGER_INVALID, CALIBRATION_UNVERIFIED, CAPTURE_DURATION_NOT_DECLARED, DEVICE_IDENTITY_MISSING, HARDWARE_CONFIG_NOT_VERIFIED, INDEPENDENT_RUN_POPULATION_INSUFFICIENT, NO_ELIGIBLE_RUNS_FOR_DECLARED_SCENARIO, RUN_IDENTITY_UNRESOLVED, RUN_MANIFEST_LINKAGE_NOT_PROVIDED, SCENARIO_VALIDITY_NOT_GRANTED, TIMING_INTEGRITY_FAILED |
| `PREDICTIVE_DATASET_READINESS` | **NOT_READY** | BLOCKING | ABSOLUTE_TIME_NOT_EVIDENCED, AUTHORITY_A_LEDGER_INVALID, CALIBRATION_UNVERIFIED, CAPTURE_DURATION_NOT_DECLARED, DEVICE_IDENTITY_MISSING, GATE_B_NOT_GREEN, HARDWARE_CONFIG_NOT_VERIFIED, INDEPENDENT_RUN_POPULATION_INSUFFICIENT, NO_ELIGIBLE_RUNS_FOR_DECLARED_SCENARIO, RUN_IDENTITY_UNRESOLVED, RUN_MANIFEST_LINKAGE_NOT_PROVIDED, SCENARIO_VALIDITY_NOT_GRANTED, TIMING_INTEGRITY_FAILED |
| `SPLIT_FEASIBILITY` | **RED** | BLOCKING | SPLIT_POPULATION_INSUFFICIENT |

A RED physical gate cannot become GREEN because other gates are GREEN. W08 software verification is reported separately from the physical-data verdict.

## 3. Run validation

| Source | Run | Scenario | A ledger | B eligibility | Blocking checks |
|---|---|---|---|---|---|
| `evidence/A/W09/exports/CG-S1-H8C-600S.json` | `UNRESOLVED` | `S1` | INVALID | **BLOCKED** | RUN_IDENTITY_CARRIED, DEVICE_IDENTITY_CARRIED, RUN_MANIFEST_LINKED, CAPTURE_DURATION_DECLARED, A_LEDGER_VERDICT, A_SCENARIO_SCOPE_GRANTED, HARDWARE_CONFIG_VERIFIED, CALIBRATION_VERIFIED, ABSOLUTE_TIME_FOR_CLAIM, TIMING_INTEGRITY |

### Reason codes and evidence

#### `evidence/A/W09/exports/CG-S1-H8C-600S.json`

- Source SHA-256: `f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb`
- Physical acquisition identity: `session|56044b74`
- Identity: run=None device=None boot='56044b74'
- Configuration: hardware='CG-HW-001' (DECLARED_NOT_VERIFIED) calibration=None (NOT_AVAILABLE) firmware='cg-w04-0.1.0'
- Time: domain='BOOT_SCOPED_UPTIME' clock_sync='NOT_EVIDENCED'
- A ledger: INVALID (AUTHORITY_A_LEDGER_INVALID, run_id_status=UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID: source run_id segments ['run-00000000', 'run-00000001'] under one boot_id are not independent runs and no joined run_id exists in the source, so none can be published for a join, majority of frames unusable)
- Event coverage: the declared scenario does not require a disturbance event
- Reason codes: ABSOLUTE_TIME_NOT_EVIDENCED, AUTHORITY_A_LEDGER_INVALID, CALIBRATION_UNVERIFIED, CAPTURE_DURATION_NOT_DECLARED, DEVICE_IDENTITY_MISSING, HARDWARE_CONFIG_NOT_VERIFIED, RUN_IDENTITY_UNRESOLVED, RUN_MANIFEST_LINKAGE_NOT_PROVIDED, SCENARIO_VALIDITY_NOT_GRANTED, TIMING_INTEGRITY_FAILED

## 4. Completeness evaluation

| Dimension | Status | Threshold | Expected | Observed | Missing | Invalid | Fraction |
|---|---|---|---|---|---|---|---|
| `WHOLE_CAPTURE_COMPLETENESS` | NOT_EVALUABLE | 0.950000 (PROPOSED) | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE |
| `CRITICAL_CHANNEL_COMPLETENESS` | NOT_EVALUABLE | 0.990000 (PROPOSED) | NOT_ESTIMABLE | 0 | 0 | 0 | NOT_ESTIMABLE |
| `PRE_EVENT_BASELINE_COMPLETENESS` | NOT_APPLICABLE | 0.950000 (PROPOSED) | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE |
| `PRIMARY_EVENT_WINDOW_COMPLETENESS` | NOT_APPLICABLE | 0.990000 (PROPOSED) | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE |
| `POST_EVENT_OR_RECOVERY_COMPLETENESS` | NOT_APPLICABLE | 0.900000 (PROPOSED) | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE | NOT_ESTIMABLE |
| `TIMING_ALIGNMENT_COMPLETENESS` | NOT_EVALUABLE | NOT_ESTIMABLE (UNRESOLVED) | 956 | 956 | 0 | 0 | NOT_ESTIMABLE |

Whole-capture completeness never substitutes for event-window completeness; missing critical samples are counted distinctly and are never converted to zero.

## 5. Gate evidence and required next evidence

### `GATE_B_PHYSICAL_DATA`

- Observed status: **RED**
- Population: 1 candidate run(s); 0 eligible
- Required checks: A_LEDGER_VALID, PHYSICAL_RUN_IDENTITY, HARDWARE_AND_CALIBRATION_VERIFIED, REQUIRED_CHANNELS_QUALIFIED, EVENT_COMPLETENESS_FOR_DECLARED_SCENARIO, RUN_MANIFEST_LINKAGE, INDEPENDENT_RUN_POPULATION, NO_DUPLICATE_VIEW_CONFLICT
- Evidence paths: evidence/A/W09/exports/CG-S1-H8C-600S.json
- Evidence SHA-256: f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb
- Allowed uses: diagnostic QA of structurally valid captures
- Prohibited uses: predictive model training or benchmark claims, locked test or Gate C evidence, any claim that physical repeatability is established
- Next evidence required: A-valid, independently identified runs with verified hardware, calibration and clock evidence; required event coverage; run manifest linkage; and at least 3 independent run(s) for the declared scenario

### `PREDICTIVE_DATASET_READINESS`

- Observed status: **NOT_READY**
- Population: 1 candidate run(s); 0 eligible
- Required checks: GATE_B_PHYSICAL_DATA_GREEN
- Evidence paths: evidence/A/W09/exports/CG-S1-H8C-600S.json
- Evidence SHA-256: f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb
- Allowed uses: dataset readiness reporting
- Prohibited uses: model training while NOT_READY
- Next evidence required: a GREEN Gate B physical-data decision for the declared population

### `SPLIT_FEASIBILITY`

- Observed status: **RED**
- Population: 1 candidate run(s); 0 eligible
- Required checks: INDEPENDENT_RUN_GROUPS, PAIR_LINEAGE_PRESERVED, NO_REPEATED_VIEW_GROUPS, P1_P2_P3_DISJOINT, P3_NOT_FROZEN
- Evidence paths: evidence/A/W09/exports/CG-S1-H8C-600S.json
- Evidence SHA-256: f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb
- Allowed uses: none
- Prohibited uses: frozen locked-test IDs, model selection against test outcomes
- Next evidence required: enough independently valid physical runs to populate three non-empty grouped partitions

## 6. Split feasibility

**SPLIT_FEASIBILITY = `NOT_FEASIBLE`**

- P1 training assignments: none
- P2 held-back validation assignments: none
- P3 locked-test planning candidates: none (`PLANNING_CANDIDATES_ONLY_NOT_A_LOCKED_TEST`)
- Reasons: SPLIT_POPULATION_INSUFFICIENT, NO_ELIGIBLE_RUNS_FOR_DECLARED_SCENARIO

No final test ID list is created or frozen. `development-split-plan-W08.md` carries the planning detail.

## 7. W07 physical-repeatability evidence

- Verdict: `NOT_ESTABLISHED`; qualified independent runs: 0; independent physical sources: 1
- Reason codes: ADMISSION_NOT_PHYSICALLY_QUALIFIED, A_LEDGER_NOT_VALID, CALIBRATION_IDENTITY_MISSING, DEVICE_IDENTITY_MISSING, HARDWARE_CONFIG_NOT_VERIFIED, MINIMUM_INDEPENDENT_RUNS_NOT_MET, NO_QUALIFIED_INDEPENDENT_RUNS, RUN_IDENTITY_UNRESOLVED, SCENARIO_NOT_CERTIFIED

## 8. Limitations

- A scientific RED is a successful software result, not a CLI failure.
- No locked test manifest is created, inspected or frozen by W08.
- Synthetic controls never enter the physical dataset or the real split.
- A GREEN W08 software gate does not make the physical data GREEN.
- Completeness uses the observed modal cadence; the project has not frozen a cadence tolerance, so timing adequacy remains a separate scientific decision.
- A capture that starts late relative to the planned experiment start is not detectable from boot-relative durations alone; a planned start anchor is required for that claim.
- The software gate is earned by the validator; the CLI additionally verifies written artifact hashes and report/CSV agreement.
- The A W09 export and validity index were consumed read-only.
- No run manifest is fabricated; missing linkage is reported.
