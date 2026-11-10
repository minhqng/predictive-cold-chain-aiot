# W23 dataset card — actual datasets and eligibility states

> **Task:** B-W23-01 · **Package:** Package A (software evidence) ·
> **Milestone:** B-W23-01…05.
>
> This card describes the datasets that actually exist in the repository. It does
> not describe an imagined final physical training population. Documentation
> completeness is not data scientific eligibility.

```text
DATASET_CARD = DOCUMENTED

REAL_PREDICTIVE_DATASET = NOT_ADMITTED

LOCKED_REAL_PREDICTIVE_TEST = NOT_EXECUTED
```

## 1. Dataset identities

These are five distinct populations. They are never combined into one training
population, and no sample from one population is re-labelled as another.

| ID | Dataset | Evidence class | State |
|---|---|---|---|
| D1 | `W11_EXPANDED_SYNTHETIC_GROUPED` (`coldguard-w11-synthetic-grouped-v1`) | `SYNTHETIC_SOFTWARE_CONTROL_ONLY` | development fixture, used by the W15 candidate |
| D2 | Member A recorded physical capture/segment package (`CG-S1-H8C-600S` and the W13 export set) | `PHYSICAL_MEASUREMENT_DIAGNOSTIC_ONLY` | 0 predictive-eligible runs; Gate B `RED` |
| D3 | W21 bounded on-device diagnostic observations (`A-W21-02`, `A-W21-03`) | `ON_DEVICE_SOFTWARE_INJECTION` | one independent session; output stage compiled out |
| D4 | Future physical predictive development data | — | `NOT_ADMITTED` |
| D5 | Future physical paired campaign outcome population | — | absent; 0 accepted pairs; campaign `NOT_AUTHORIZED` |

D1 is generated deterministically in memory by
`ml/src/coldguard_ml/feature_fixtures.py`
(SHA-256 `711bf4a0acd9913207c430a6188640afb2e9ff25feb156743de58a241ec6e837`);
no raw fixture payload file exists in the repository. D2 is an A-owned external
capture package; only its metadata and permitted diagnostic exports are consumed
by B. D3 is an A-owned diagnostic recording; B consumes its pinned summary
metadata only. D4 and D5 do not exist.

### Purpose and coverage (Doc 03 §126)

| Field | D1 synthetic | D2 physical capture package | D3 on-device diagnostic | D4 / D5 |
|---|---|---|---|---|
| Purpose | synthetic software-control development and grouped evaluation | physical measurement/diagnostic QA only; the declared S1 predictive purpose is blocked | bounded degraded-sensor/PZEM diagnosis | final physical predictive development / paired outcome population |
| Date range | no wall-clock date (deterministic in-memory fixture) | 2026-11-02 for the W05 candidate capture; 2026-11-07 for the W13 export set (source unavailable) | 2026-11-08 declared session family; exact start/end timestamps are not in the consumed metadata | none |
| Scenarios | synthetic S1/S2 pair arms | S1 normal-baseline candidate; W13 set: 4 accepted S1 windows, 5 accepted S2 windows | single-DS18B20 T1 role and PZEM transport software injection; not a physical scenario | none |
| Sampling cadence | synthetic fixture cadence; not a physical cadence claim | W05 records nominal cadence `NOT_ESTIMABLE`; the capture is A-invalid | 100 recorded frames (50 fault + 50 recovery); no certified cadence | none |
| Invalid / aborted attempts | 0 (deterministic fixture) | 1 candidate boot / 2 unresolved run-ID segments; 0 eligible; W13 set has 18 segments / 8 boots and 0 predictive-eligible runs | 2 test IDs in 1 boot / 1 raw log; 1 independent session | 0 |

## 2. Provenance

### D1 — W11 synthetic grouped fixture

| Field | Value |
|---|---|
| Source owner | Member B |
| Source commit/ref | W11 branch `feat/b-w11-grouped-xgboost-benchmark`; manifest `ml/reports/W11/benchmark-manifest-W11.json` SHA-256 `855c5beb55f15c6e…` |
| Manifest identity | `W11_EXPANDED_SYNTHETIC_GROUPED`, layer `coldguard-w11-grouped-benchmark-v1` |
| Raw-data availability | generated in memory; no locked-test payload file; the fixture generator is the reproducible source |
| Run/boot/session identity | 20 declared run IDs in 10 pair groups; 4 locked-test runs; synthetic run identity only |
| Hardware configuration | none (synthetic software fixture) |
| Firmware version | none |
| Sensor role map | fixture channels mirror the registry role names; not physical probes |
| Calibration status | not applicable (synthetic) |
| Time-domain status | synthetic source-declared relative time |
| Quality flags | censored labels excluded; no physical quality flags exist |
| Source checksums | fixture generator `711bf4a0…`; benchmark manifest `855c5beb…`; fold manifest `702623f1…`; registry `f1c716a6…` (schema `1d36d338…`); config `01e48a55…` (config SHA-256 `4369f39f…`) |

### D2 — Member A recorded physical capture/segment package

| Field | Value |
|---|---|
| Source owner | Member A |
| Source commit/ref | A W09 export consumed by W05/W08/W09; A W13 timing report `evidence/A/W13/plant-timing-report.json` SHA-256 `2826a710…`; A W20 wave-2 index `evidence/A/W20/campaign-wave2-index.json` SHA-256 `4c58e48f…` |
| Manifest identity | `CG-S1-H8C-600S` export SHA-256 `f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb`; A run index SHA-256 `eb71d3f58004a25e60315b39ed88e33daa7e069a7a1fc3df391713cfce33b5af` |
| Raw-data availability | physically measured; the raw export is present read-only in the shared A evidence tree and is **not duplicated or copied into the W23 package** |
| Run/boot/session identity | W05 candidate capture: one boot `56044b74`, two source run-ID segments (`run-00000000`, `run-00000001`) **under one boot**; W13 export set: 18 rows/segments across 8 distinct boots |
| Hardware configuration | `CG-HW-001`; the A ledger does not publish a certified hardware identity for this capture |
| Firmware version | `cg-w06-0.1.0` in the W21 session; not certified for the W05 capture |
| Sensor role map | as-built: T1 `CHAMBER_CENTER`, T2 `TEC_HOT_SIDE`, T3 `CHAMBER_BOTTOM`, T4 `CHAMBER_NEAR_DOOR`; T1/T3/T4 are chamber air, T2 is not |
| Calibration status | `NOT_AVAILABLE` (W08 run record) |
| Time-domain status | `BOOT_SCOPED_UPTIME`; absolute event time not evidenced |
| Quality flags | A ledger `INVALID`; run identity `UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID`; majority of frames unusable in the candidate capture |
| Source checksums | export `f6235e23…`; A run index `eb71d3f5…`; W05 QA manifest `66343133…`; W07 EDA manifest `3252e9f3…`; W08 Gate B manifest `1dde8ea3…`; W09 baseline manifest `a6e4b39d…`; W13 horizon manifest `02a76660…` |

### D3 — W21 bounded on-device diagnostic observations

| Field | Value |
|---|---|
| Source owner | Member A (acceptance evaluator lineage `feat/a-w21-evidence-final @ 5fd89fb`, **not on main**) |
| Source commit/ref | declared result commit `cd1b40e08456a0a088f131cbdd2e1ef3b92052cc`; B manifest `ml/reports/W21/w21-manifest.json` SHA-256 `5b78141d…` |
| Manifest identity | `A-W21-02` + `A-W21-03` combined session `W21-02_W21-03_combined` |
| Raw-data availability | raw log declared at 371 291 bytes, SHA-256 `faf008eb6c7e250c8b8f98385e6eb3817b1084771a56d800a3735c576c7106fa`; the declared `evidence/A/W21/results/` payload is **not present in this checkout** (`SOURCE_UNAVAILABLE`) |
| Run/boot/session identity | boot `4cf9be5f`, boot count `181`, device `coldguard-001`; two test IDs share **one** boot and **one** raw log; independent session count = **1** |
| Hardware configuration | `CG-HW-001` |
| Firmware version | `cg-w06-0.1.0`, binary SHA-256 `e1073935168c01be029c23a87f6f012d852016deac0afb672437f234a269206b` |
| Sensor role map | same as-built map; ROMs T1 `287088CA00000051`, T2 `28AEBF2200000006`, T3 `28CBE9CA00000072`, SPARE/T4 `283BE5C9000000A9`; unchanged during injection |
| Calibration status | not established |
| Time-domain status | device boot-scoped; no absolute UTC evidence |
| Quality flags | injected T1 invalid / PZEM unavailable; output stage `COMPILED_OUT`; TEC actuation `NONE`; fuse `OUT` |
| Source checksums | manifest `5b78141d…`; source register `0f742f5c00ba8294a2e6df21bb260f2fe1c90d526ac6aabb1953613b61507735`; A W21 summaries `3cd6b19b…` (SHA256SUMS), `f93d58fc…`, `c0c05f41…`, `5f77e382…` |

### D4 and D5 — absent populations

| Field | D4 future physical predictive development data | D5 future physical paired outcome population |
|---|---|---|
| Source owner | Member A / Member C / Member D as applicable | Member A / Member C / Member D as applicable |
| Source commit/ref | none | none |
| Manifest identity | none | `CG-W20-FINAL-AB-2026` campaign metadata only; `campaign_wave2_runs = []` |
| Raw-data availability | `SOURCE_UNAVAILABLE` | `SOURCE_UNAVAILABLE`; no outcome export is admitted |
| Independent units | UNKNOWN | 0 accepted pairs; pair target `UNKNOWN_UNFROZEN` |
| Status | `NOT_ADMITTED` | `MISSING_REQUIRED_EVIDENCE` |

## 3. Independent units

Counts are reported separately. A file name, telemetry row, feature window or
fault-injection window is never an independent run. Unknown counts remain
`UNKNOWN`.

| Unit | D1 synthetic | D2 physical capture package | D3 on-device diagnostic | D4 | D5 |
|---|---:|---:|---:|---|---|
| Records / frames | 2 896 windows generated (1 936 evaluable + 960 censored) | W05 candidate: 957 rows; W13 export set: 9 293 frames | 100 recorded frames (50 fault + 50 recovery) | UNKNOWN | — |
| Segments | 20 synthetic runs | 18 exported rows/segments | 2 test IDs | UNKNOWN | — |
| Boots | synthetic BOOT identities | 1 (candidate) / 8 (W13 set) | 1 | UNKNOWN | — |
| Independent runs | 16 development runs (8 pairs) | **0 predictive-eligible** | **1 independent session** | 0 admitted | 0 |
| Pair groups | 10 declared pairs (8 development + 2 locked test) | 0 accepted pairs | 0 | 0 | 0 accepted |
| Eligible supervised development | 16 runs / 8 pair groups | 0 | 0 | 0 | 0 |
| Locked-test membership | 4 runs / 2 pairs (synthetic only) | none | none | none | none |
| Accepted final physical pairs | — | 0 | 0 | 0 | 0 |

Do not read these counts as: 18 segments = 18 independent runs; 100 frames = 100
experiments; 2 W21 test IDs = 2 independent sessions; or 8 boots = 8 eligible
predictive runs. The W13 independence statement is explicit: 18 exported
rows/segments span 8 distinct boots.

## 4. Split manifest

### D1 actual synthetic split

| Item | Value |
|---|---|
| Train runs | `CG-W11-S1-003/004/008/009`, `CG-W11-S2-003/004/008/009` (4 pairs / 8 runs) |
| Validation runs | `CG-W11-S1-005/006/007/010`, `CG-W11-S2-005/006/007/010` (4 pairs / 8 runs) |
| Locked-test runs | `CG-W11-S1-001/002`, `CG-W11-S2-001/002` (2 pairs / 4 runs) — declared membership only; payload never opened |
| Pair lineage | one effective group per S1/S2 pair; both arms stay on the same partition side |
| Split seed / method | seed `42`; grouped by `run_id + pair_id`; `GroupKFold`-style 4-fold development CV with 6 train groups / 2 validation groups per fold |
| Split revision/hash | W11 fold manifest `702623f1…`; W11 manifest `855c5beb…`; W15 population hash `6d6d265d03bd664bd808652789c48af3c79a508c01625bc445f5c5c427f4f889` |
| Locked-test state | `test_partition_used = false`; no evaluation receipt exists |

### D2–D5 actual split

No physical split exists. W08 records `SPLIT_FEASIBILITY = NOT_FEASIBLE`,
`candidate_count = 1`, `eligible_count = 0`, and no `split_seed`. The Doc 03 §48
16/4/4 shape is an illustrative planning shape, not an executed split. W16’s
locked-test manifest is a **pre-registration only** (`evaluation_status =
NOT_RUN`, `holdout_opened = false`).

## 5. Target and label

| Field | Value | Status |
|---|---|---|
| Target definition | binary critical event in `(t, t+H]` on a development-candidate label spec | `DEVELOPMENT_CANDIDATE_NOT_FROZEN` |
| Label spec | `coldguard-w11-development-label-v1` | frozen software identity only |
| Representative temperature | not selected | `DEVELOPMENT_CANDIDATE_NOT_SELECTED` |
| Critical threshold `T_critical` | `null` | `NOT_FROZEN` |
| Horizon | 60 s | `ENGINEERING_REFERENCE_HORIZON_NOT_PRIMARY_FROZEN` |
| Event timing | source-declared within run; censored samples excluded | software identity |
| Censoring | 960 W11 windows excluded (60 per development run) | recorded |
| Untrusted labels | no real eligible population; physical labels do not exist | `NOT_ADMITTED` |
| Physical intervention restrictions | Controller B interventional trajectories refused for observational training; closed-loop runs excluded from naive EWT | enforced |

The 60 s horizon is a software-development reference inherited from W11. It is
not a physically justified primary horizon and must not be presented as measured
early-warning time. The physical critical target remains a Member D freeze
dependency.

## 6. Feature contract

| Field | Value |
|---|---|
| Registry version | `CG-FEAT-1.0`, `registry_status = FROZEN_DEFINITIONS` |
| Registry hash | file `f1c716a61c1d5c8eeaf0ff6e9596320c6df0bb47bce11ece0e67c038c72ffdbb`; schema hash `1d36d338f35dd448b8c680075fdbe26785384f418a4ef36769b234c7101c83c9` |
| Ordered model features | 28 features; ordered list hash `98491993d95ba78292cc245d637a1832ebdfb80b1eb026361e39926fb331223c` |
| Temperature roles | T1/T3/T4 are **chamber-air** probes (center/bottom/near-door); **T2 is TEC hot-side** and is not chamber air |
| Door state | trusted only when state is `OPEN`/`CLOSED`, door quality `VALID`, and polarity attested; `UNKNOWN` is never `CLOSED` |
| Applied/electrical provenance | `POWER_PATH` applied state/duty in A3b; `PZEM_COOLING_BRANCH` voltage/current/power/energy; a command is not proof of current or cooling |
| PZEM missingness | only `VALID` electrical samples produce electrical features; `UNKNOWN`/`INVALID`/`DEGRADED` remain missing and are never zero; counter reset/rollover → `MISSING_COUNTER_RESET`, never negative consumption |
| Causal windowing | `(t - lookback_s, t]`, actual event time, `max_gap_s = 5.0`, no boot crossing, no future values; explicit missing is never zero-filled |
| Model config | `xgb-v1-config.yaml` file `01e48a55…`, config SHA-256 `4369f39f…` |

## 7. Invalidations and limitations

1. **Missing absolute event-time/clock synchronization.** The physical candidate
   is on a boot-scoped uptime clock; absolute UTC and clock-sync evidence are
   absent.
2. **Run/boot identity ambiguity.** The candidate capture contains two source
   run-ID segments under one boot; no joined run ID exists, so it cannot be
   published as an independent run.
3. **Calibration lineage unavailable.** No calibration identity is recorded for
   the physical candidate; sensor placement is an A operator as-built role
   record, not independently measured calibration.
4. **Untrusted sensor quality.** T1 and PZEM injections in W21 are diagnostic
   software injections; they do not establish real sensor-failure behaviour or
   model robustness.
5. **Duplicated source lineage.** 18 W13 rows/segments are not 18 independent
   runs; two exported views of one physical source are refused as independent
   groups.
6. **Intervention-contaminated trajectories.** Controller B interventional
   trajectories cannot be used as observational predictive training data; a
   closed-loop B trajectory cannot provide a naive no-control counterfactual.
7. **Incomplete event coverage.** 4 S1 windows and 5 S2 windows were accepted
   for diagnostic analysis; there is no certified S2 event population and no
   physical positive-event development set.
8. **Independent-N limitation.** D1 has 8 development pair groups and 4
   correlated folds — not 4 physical experiments. D3 has one independent
   session. D2 and D5 have zero accepted independent pairs.
9. **Synthetic AP saturation.** Synthetic AP = 1.0 is a software control, not
   physical predictive performance.
10. **No biological/product-quality ground truth.** Thermal/energy measurements
    do not establish product quality.

## 8. Disposition

```text
DATASET_CARD = DOCUMENTED

D1 SYNTHETIC DEVELOPMENT FIXTURE = DOCUMENTED
D2 PHYSICAL CAPTURE PACKAGE = DIAGNOSTIC_ONLY / 0 ELIGIBLE
D3 W21 ON-DEVICE DIAGNOSTIC = BOUNDED / 1 SESSION
D4 REAL PREDICTIVE DEVELOPMENT DATA = NOT_ADMITTED
D5 REAL PAIRED OUTCOME POPULATION = MISSING_REQUIRED_EVIDENCE

REAL_PREDICTIVE_DATASET = NOT_ADMITTED

LOCKED_REAL_PREDICTIVE_TEST = NOT_EXECUTED
```

This card documents what exists. It does not admit D2 or D3 as predictive
training data, and it does not turn D1 into physical evidence.

## 9. Binding sources

- `ml/reports/W11/benchmark-manifest-W11.json` (`855c5beb…`)
- `ml/reports/W11/cv-fold-manifest.yaml` (`702623f1…`)
- `ml/reports/W08/gate-b-manifest-W08.json` (`1dde8ea3…`)
- `ml/reports/W13/horizon-manifest-W13.json` (`02a76660…`)
- `ml/reports/W16/locked-test-manifest-W16.json` (`6e7e7f23…`)
- `ml/reports/W21/w21-manifest.json` (`5b78141d…`)
- `ml/feature-registry-v1.yaml` (`f1c716a6…`)
- `ml/reports/W15/model/model-manifest-W15.json` (`85960c82…`)
- `ml/reports/W23/evidence-package-W23.json`
