# Gate B reassessment — existing physical sources

> The canonical validator is W08, run unchanged. This file is a reassessment record, not a replacement validator. The delivery statuses below are not Gate B statuses.

## 1. Canonical run

| field | value |
|---|---|
| validator | ml/scripts/gate-b-readiness-W08.py |
| command | python scripts/gate-b-readiness-W08.py --source evidence/A/W09/exports/CG-S1-H8C-600S.json --a-run-index evidence/A/W09/s1-run-index.json --scenario S1 --out <GATE_B_SCRATCH> --repository-revision a9dacbe984b3287c7b7b0cdce8416552f66d3808 |
| source | evidence/A/W09/exports/CG-S1-H8C-600S.json |
| source SHA-256 | f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb |
| validator exit code | 0 |
| W08 software verification | GREEN |
| GATE_B_PHYSICAL_DATA | RED |
| PREDICTIVE_DATASET_READINESS | NOT_READY |
| SPLIT_STATUS | RED |
| SPLIT_FEASIBILITY | NOT_FEASIBLE |
| population | 1 candidate run(s); 0 eligible |
| physical reason codes | ABSOLUTE_TIME_NOT_EVIDENCED, AUTHORITY_A_LEDGER_INVALID, CALIBRATION_UNVERIFIED, CAPTURE_DURATION_NOT_DECLARED, DEVICE_IDENTITY_MISSING, HARDWARE_CONFIG_NOT_VERIFIED, INDEPENDENT_RUN_POPULATION_INSUFFICIENT, NO_ELIGIBLE_RUNS_FOR_DECLARED_SCENARIO, RUN_IDENTITY_UNRESOLVED, RUN_MANIFEST_LINKAGE_NOT_PROVIDED, SCENARIO_VALIDITY_NOT_GRANTED, TIMING_INTEGRITY_FAILED |
| predictive reason codes | ABSOLUTE_TIME_NOT_EVIDENCED, AUTHORITY_A_LEDGER_INVALID, CALIBRATION_UNVERIFIED, CAPTURE_DURATION_NOT_DECLARED, DEVICE_IDENTITY_MISSING, GATE_B_NOT_GREEN, HARDWARE_CONFIG_NOT_VERIFIED, INDEPENDENT_RUN_POPULATION_INSUFFICIENT, NO_ELIGIBLE_RUNS_FOR_DECLARED_SCENARIO, RUN_IDENTITY_UNRESOLVED, RUN_MANIFEST_LINKAGE_NOT_PROVIDED, SCENARIO_VALIDITY_NOT_GRANTED, TIMING_INTEGRITY_FAILED |
| split reason codes | SPLIT_POPULATION_INSUFFICIENT |

## 2. Old refusal versus newly available evidence

The old refusal was the A ledger `INVALID` / unresolved run identity on the W05 candidate capture (`UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID`, majority of frames unusable). The newly available authoritative evidence is the merged A 20261107 package: **18 rows/segments**, **9293 frames**, **8 distinct boots**, **4 A-accepted S1 windows**, **5 A-accepted S2 windows**, with per-file SHA-256 pins verified against the manifest.

Checks now satisfied:

- physical measurements and per-channel statuses are present;
- A accepted the S1/S2 windows as scenarios, not as independent runs;
- the five S2 windows carry recorded door transitions and operator command evidence;
- source bytes, manifest and run index hashes match their pins;
- cooling-branch observations exist for H8-C, H8-E and W07 trials.

Remaining failures (all still blocking):

- no device wall clock or clock-sync evidence for physical event UTC;
- no calibration identity and no certified device identity;
- run IDs are `UNSET` or segment-only;
- repeated windows share boots, so they are not independent runs;
- the critical Tmean threshold / representative T define no label;
- the current W08 intake consumes the W09 export format and does not admit the 18-row normalized package; no weaker validator was invented.

## 3. Actual canonical outcome

```text
GATE_B_PHYSICAL_DATA = RED
PREDICTIVE_DATASET_READINESS = NOT_READY
SPLIT_FEASIBILITY = NOT_FEASIBLE
18_ROW_PACKAGE_ADMITTED = NO
W08_EVALUATED = W05_CANDIDATE_ONLY
CANONICAL_VALIDATOR_INTAKE = W09_RUN_EXPORT_V2
```

The W08 software verification is `GREEN`; a software pass does not turn the physical gate green.

## 4. Delivery statuses are separate

```text
EXISTING_DATA_REUSE = READY_FOR_BOUNDED_ANALYSIS
DEADLINE_DEMO_PACKAGE = READY
```

These statuses describe the usability of the existing-data package for a bounded descriptive demonstration. They do not change Gate B, do not authorize model training and do not authorize Controller B.

