# W13 horizon study — evidence reconciliation, candidates, grouped sensitivity

Layer `coldguard-w13-horizon-engineering-v1`; label spec `coldguard-w13-horizon-sensitivity-v1`.

**Scientific decision: PROVISIONAL_CANDIDATE_ONLY.** Primary horizon: not selected, not frozen. Software study completed on the synthetic development population only; the real physical population is refused by the admission ladder with explicit reasons.

## Phase A — evidence reconciliation

Source: `origin/main@d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85` (merged PR #91 package), consumed through a read-only `git archive` export; the B stack was not rebased. Pins: run_index `53d476747c4a865ddec09492c9c49601a72ab766e9862faac0a2c9a43a22bbb4`, manifest `5273e528e6505caf55dec79a5fccbe0e6407161c1fedb864b52a7160706cc72d`.

| Quantity | Value |
|---|---|
| Exported rows/segments | 18 |
| Distinct boots (independence ceiling) | 8 |
| Frames total | 9293 |
| A-accepted S1 windows | 4 |
| A-accepted S2 windows (door + timing) | 5 |
| B predictive-eligible runs | 0 |

18 exported rows/segments span 8 distinct boots; rows are never counted as independent runs.

### Per-source classification

| run | scenario | A classification | B classification | boot | frames | permitted use |
|---|---|---|---|---|---:|---|
| W10-02 | S2_TIMING | DATASET_ACCEPTED_S2 | PHYSICAL_BUT_NOT_ELIGIBLE | 73311d0c | 120 | SCENARIO_QA_AND_DOOR_DISTURBANCE_CHARACTERIZATION |
| W10-03-run1 | S2_DOOR | DATASET_ACCEPTED_S2 | PHYSICAL_BUT_NOT_ELIGIBLE | 73311d0c | 300 | SCENARIO_QA_AND_DOOR_DISTURBANCE_CHARACTERIZATION |
| W10-03-run2 | S2_DOOR | DATASET_ACCEPTED_S2 | PHYSICAL_BUT_NOT_ELIGIBLE | 73311d0c | 300 | SCENARIO_QA_AND_DOOR_DISTURBANCE_CHARACTERIZATION |
| W10-03-run3 | S2_DOOR | DATASET_ACCEPTED_S2 | PHYSICAL_BUT_NOT_ELIGIBLE | 73311d0c | 300 | SCENARIO_QA_AND_DOOR_DISTURBANCE_CHARACTERIZATION |
| W10-03-run4 | S2_DOOR | DATASET_ACCEPTED_S2 | PHYSICAL_BUT_NOT_ELIGIBLE | 73311d0c | 300 | SCENARIO_QA_AND_DOOR_DISTURBANCE_CHARACTERIZATION |
| S2-20261107-between-window | S2_OUTSIDE | REAL_FRAMES_OUTSIDE_TIMED_WINDOWS | DIAGNOSTIC_ONLY | 73311d0c | 346 | NEVER_COUNTED_AS_AN_INDEPENDENT_RUN |
| trial2 | S1 | DATASET_ACCEPTED_S1 | PHYSICAL_BUT_NOT_ELIGIBLE | 4a21a645 | 600 | SCENARIO_QA_AND_BASELINE_CHARACTERIZATION |
| trial3 | S1 | DATASET_ACCEPTED_S1 | PHYSICAL_BUT_NOT_ELIGIBLE | 4a21a645 | 600 | SCENARIO_QA_AND_BASELINE_CHARACTERIZATION |
| trial4 | S1 | DATASET_ACCEPTED_S1 | PHYSICAL_BUT_NOT_ELIGIBLE | 4a21a645 | 601 | SCENARIO_QA_AND_BASELINE_CHARACTERIZATION |
| S1-20261107-between-window | S1_OUTSIDE | REAL_FRAMES_OUTSIDE_TIMED_WINDOWS | DIAGNOSTIC_ONLY | 4a21a645 | 62 | NEVER_COUNTED_AS_AN_INDEPENDENT_RUN |
| trial1-imported | S1 | DATASET_ACCEPTED_S1 | PHYSICAL_BUT_NOT_ELIGIBLE | c20d17f6 | 600 | SCENARIO_QA_AND_BASELINE_CHARACTERIZATION |
| H8-C-600s-TEC-100pct | COOLING_STEP | REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED | PHYSICAL_BUT_NOT_ELIGIBLE | 56044b74 | 957 | PLANT_TIMING_ANALYSIS_ONLY |
| H8-E-1800s-TEC-100pct | COOLING_STEP_1800S | REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED | PHYSICAL_BUT_NOT_ELIGIBLE | c4ff0ab3 | 2915 | PLANT_TIMING_ANALYSIS_ONLY |
| a-w07-02-run-1-4b555191 | W07_PASSIVE_REPEAT | REAL_PHYSICAL_REPEATS / INDEPENDENCE_CAVEAT | PHYSICAL_BUT_NOT_ELIGIBLE | 4b555191 | 300 | DIAGNOSTIC_CONTINUITY_ONLY_NO_FULL_PROBE_ROWS |
| a-w07-02-run-2-4b555191 | W07_PASSIVE_REPEAT | REAL_PHYSICAL_REPEATS / INDEPENDENCE_CAVEAT | PHYSICAL_BUT_NOT_ELIGIBLE | 4b555191 | 300 | DIAGNOSTIC_CONTINUITY_ONLY_NO_FULL_PROBE_ROWS |
| a-w07-02-run-3-4b555191 | W07_PASSIVE_REPEAT | REAL_PHYSICAL_REPEATS / INDEPENDENCE_CAVEAT | PHYSICAL_BUT_NOT_ELIGIBLE | 4b555191 | 300 | DIAGNOSTIC_CONTINUITY_ONLY_NO_FULL_PROBE_ROWS |
| a-w07-03-trial-2-be89bf4a | COOLING_STEP_500PERMILLE | REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED | PHYSICAL_BUT_NOT_ELIGIBLE | be89bf4a | 196 | PLANT_TIMING_ANALYSIS_ONLY |
| a-w07-03-trial-3-f44c9bed | COOLING_STEP_500PERMILLE | REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED | PHYSICAL_BUT_NOT_ELIGIBLE | f44c9bed | 196 | PLANT_TIMING_ANALYSIS_ONLY |

### Predictive admission refusal reasons (all real runs)

- `EVENT_UTC_UNAVAILABLE_DEVICE_HAS_NO_WALL_CLOCK`
- `HOST_RECEIPT_TIME_IS_NOT_PHYSICAL_EVENT_TIME`
- `CLOCK_SYNC_NOT_EVIDENCED_IN_PACKAGE`
- `RUN_IDENTITY_UNRESOLVED_FOR_CG_RUN_PATTERN`
- `CALIBRATION_TRACEABILITY_ABSENT_FROM_PACKAGE_SCHEMA`
- `SEGMENTS_SHARE_BOOTS_ROWS_ARE_NOT_INDEPENDENT_RUNS`
- `CRITICAL_CRITERION_AND_REPRESENTATIVE_T_NOT_FROZEN`

### Superseded / stale evidence notes (computed, A files untouched)

- evidence/A/W09/run-registry.json and evidence/A/W11/additional-valid-run-list.json record zero valid S1/S2 runs; those historical verdicts predate the merged 20261107 package and are superseded for scenario validity by A-W09-02 / A-W10-03 PASS (4 S1 windows, 4 S2 door runs). They are not rewritten, and scenario acceptance still does not grant B predictive eligibility.
- evidence/A/W13/plant-timing-report.json refuses door->critical with the reason 'no door-open event exists in any committed capture'; that reason is stale because the merged package carries 5 S2 door/timing windows. The NOT_COMPUTABLE value itself stands: the critical definition is unfrozen (D threshold pending; A-W10-05 / A-W13-03 INCOMPLETE, offline rerun once frozen).

### PR #95 supplement (cited, never consumed)

- PR #95 head `815387d19a3898e6b33ccb65758a554dd0c589e1`; merge status `OPEN_UNMERGED`; classification `NOT_VERIFIED_FOR_CANONICAL_USE`; consumed as canonical evidence: False.
- trial.json sha256 `f028441d10af53f43873000a6d16ab43e79a80f6defe0b974a6a5dc60c9d3b14`.
- 2026-11-09 passive S1 trial: capture PASS, VALID passive baseline, NOT ADMITTED to the frozen 18-row/segment export; door_status=UNVERIFIED, calibration_id=UNRECORDED, 2 PZEM timeout frames; supplementary material only, pending merge and its restrictions a-g.

### A plant timing (merged evidence/A/W13/plant-timing-report.json)

- evidence kind `HOST_ANALYSIS_OF_COMMITTED_CAPTURES`, physical_verified=false; command->electrical 1.0940 s (n=1, console START-accept anchor, +/-1 s poll quantization); command->thermal 51.0000 s for 1.0000 degC (applied-on anchor, boot 56044b74).
- cooling tau proxy 174.0000 s, recovery tau proxy 86.0000 s (uses the observed endpoints as the swing; a run that has not reached steady state under-estimates tau).
- passive drift 0.1040 degC over 3.6330 min; no passive tau asserted.
- door->critical: `NOT_COMPUTABLE` (value null; critical definition unfrozen).

## Phase B — candidate horizon screening (DERIVED, proxy-biased)

Canonical exploratory candidates 30/60/120/300 s for the fast six-litre plant (docs/03). No longer horizon is invented: the measured tau proxies are truncation-biased. AIW upper bound = H - command->thermal proxy, assuming only T_system >= 0.

| H (s) | screen | AIW upper bound (s) | H / cooling tau | rationale |
|---:|---|---:|---:|---|
| 30 | DEPRIORITIZED_PHYSICS_PROXY | -21.0000 | 0.1724 | H=30s does not exceed the measured applied-on->1 degC thermal response proxy (51s); AIW <= -21s even with zero system latency, so this horizon is deprioritized as a primary candidate and retained for sensitivity only |
| 60 | PROVISIONAL_PENDING_EVIDENCE | 9.0000 | 0.3448 | H=60s leaves at most 9s of AIW headroom before the unknown system latency; actionability is not established and the horizon stays provisional |
| 120 | PROVISIONAL_PENDING_EVIDENCE | 69.0000 | 0.6897 | H=120s leaves at most 69s of AIW headroom before the unknown system latency; actionability is not established and the horizon stays provisional |
| 300 | PROVISIONAL_PENDING_EVIDENCE | 249.0000 | 1.7241 | H=300s leaves at most 249s of AIW headroom before the unknown system latency; actionability is not established and the horizon stays provisional |

Screening status: `DERIVED_PROXY_SCREENING_NOT_A_MEASURED_VERDICT`.

- Caveat: thermal proxy is a raw first-crossing on one boot, anchored on the applied-on frame, not on a warning
- Caveat: tau proxies under-estimate tau by window truncation
- Caveat: command->electrical is n=1 on a console path, not a backend-command distribution
- Caveat: T_system is unmeasured (network command path absent); the bound assumes only T_system >= 0

## Phase C — per-horizon grouped study (synthetic software control)

Fixture `W11_EXPANDED_SYNTHETIC_GROUPED` (`coldguard-w11-synthetic-grouped-v1`); label spec `coldguard-w13-horizon-sensitivity-v1`; one-factor-at-a-time: only the label horizon changes, the W11 development split/folds/seed/features stay frozen. Population: SYNTHETIC_DEVELOPMENT — never a physical benchmark.

### Label populations per horizon

| H (s) | evaluable | positive | negative | prevalence | censored excl. | untrusted excl. | leakage audit |
|---:|---:|---:|---:|---:|---:|---:|---|
| 30 | 2416 | 240 | 2176 | 0.0993 | 480 | 0 | PASS |
| 60 | 1936 | 480 | 1456 | 0.2479 | 960 | 0 | PASS |
| 120 | 1288 | 800 | 488 | 0.6211 | 1608 | 0 | PASS |
| 300 | 800 | 800 | 0 | 1.0000 | 2096 | 0 | NOT_RUN_HORIZON_REFUSED |

Censored horizons are excluded, never labeled negative.
H=300 s benchmark evaluation is refused: W13_HORIZON_NOT_ESTIMABLE: the label configuration leaves 8 of 16 runs with zero evaluable anchors; the shared W11 grouped benchmark refuses that declared population deterministically (DEV_RUN_WITHOUT_EVALUABLE_ANCHORS) instead of dropping a run, so the horizon is not estimable under the frozen benchmark contract; the remaining evaluable population is 800 positive and 0 negative, which is single-class, so AP and event metrics stay undefined.

### Per-method fold AP (every fold reported; undefined stays undefined)

| H (s) | method | fold | fit | AP | event recall | false warn/h | missed | unmatched |
|---:|---|---|---|---:|---:|---:|---:|---:|
| 30 | B0_THRESHOLD | F1 | BASELINE_REPLAY | 0.4058 | 1.0000 | 0 | 0 | 0 |
| 30 | B1_HYSTERESIS | F1 | BASELINE_REPLAY | 0.3175 | 1.0000 | 0 | 0 | 0 |
| 30 | B0_THRESHOLD | F2 | BASELINE_REPLAY | 0.4059 | 1.0000 | 0 | 0 | 0 |
| 30 | B1_HYSTERESIS | F2 | BASELINE_REPLAY | 0.2985 | 1.0000 | 0 | 0 | 0 |
| 30 | B0_THRESHOLD | F3 | BASELINE_REPLAY | 0.4062 | 1.0000 | 0 | 0 | 0 |
| 30 | B1_HYSTERESIS | F3 | BASELINE_REPLAY | 0.3529 | 1.0000 | 0 | 0 | 0 |
| 30 | B0_THRESHOLD | F4 | BASELINE_REPLAY | 0.4070 | 1.0000 | 0 | 0 | 0 |
| 30 | B1_HYSTERESIS | F4 | BASELINE_REPLAY | 0.3093 | 1.0000 | 0 | 0 | 0 |
| 30 | UNWEIGHTED | F1 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 30 | UNWEIGHTED | F2 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 30 | UNWEIGHTED | F3 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 30 | UNWEIGHTED | F4 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 30 | TRAIN_FOLD_CLASS_WEIGHT | F1 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 30 | TRAIN_FOLD_CLASS_WEIGHT | F2 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 30 | TRAIN_FOLD_CLASS_WEIGHT | F3 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 30 | TRAIN_FOLD_CLASS_WEIGHT | F4 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 60 | B0_THRESHOLD | F1 | BASELINE_REPLAY | 0.9874 | 1.0000 | 0 | 0 | 0 |
| 60 | B1_HYSTERESIS | F1 | BASELINE_REPLAY | 0.6897 | 1.0000 | 0 | 0 | 0 |
| 60 | B0_THRESHOLD | F2 | BASELINE_REPLAY | 0.9886 | 1.0000 | 0 | 0 | 0 |
| 60 | B1_HYSTERESIS | F2 | BASELINE_REPLAY | 0.6953 | 1.0000 | 0 | 0 | 0 |
| 60 | B0_THRESHOLD | F3 | BASELINE_REPLAY | 0.9889 | 1.0000 | 0 | 0 | 0 |
| 60 | B1_HYSTERESIS | F3 | BASELINE_REPLAY | 0.6840 | 1.0000 | 0 | 0 | 0 |
| 60 | B0_THRESHOLD | F4 | BASELINE_REPLAY | 0.9891 | 1.0000 | 0 | 0 | 0 |
| 60 | B1_HYSTERESIS | F4 | BASELINE_REPLAY | 0.6953 | 1.0000 | 0 | 0 | 0 |
| 60 | UNWEIGHTED | F1 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 60 | UNWEIGHTED | F2 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 60 | UNWEIGHTED | F3 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 60 | UNWEIGHTED | F4 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 60 | TRAIN_FOLD_CLASS_WEIGHT | F1 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 60 | TRAIN_FOLD_CLASS_WEIGHT | F2 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 60 | TRAIN_FOLD_CLASS_WEIGHT | F3 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 60 | TRAIN_FOLD_CLASS_WEIGHT | F4 | FIT | 1.0000 | 1.0000 | 0 | 0 | 0 |
| 120 | B0_THRESHOLD | F1 | BASELINE_REPLAY | 0.9434 | undefined | 22.6415 | 0 | 2 |
| 120 | B1_HYSTERESIS | F1 | BASELINE_REPLAY | 0.8314 | undefined | 22.6415 | 0 | 2 |
| 120 | B0_THRESHOLD | F2 | BASELINE_REPLAY | 0.9341 | undefined | 22.6415 | 0 | 2 |
| 120 | B1_HYSTERESIS | F2 | BASELINE_REPLAY | 0.8333 | undefined | 22.6415 | 0 | 2 |
| 120 | B0_THRESHOLD | F3 | BASELINE_REPLAY | 0.8595 | undefined | 22.6415 | 0 | 2 |
| 120 | B1_HYSTERESIS | F3 | BASELINE_REPLAY | 0.8295 | undefined | 22.6415 | 0 | 2 |
| 120 | B0_THRESHOLD | F4 | BASELINE_REPLAY | 0.8595 | undefined | 22.6415 | 0 | 2 |
| 120 | B1_HYSTERESIS | F4 | BASELINE_REPLAY | 0.8333 | undefined | 22.6415 | 0 | 2 |
| 120 | UNWEIGHTED | F1 | FIT | 0.9047 | undefined | 45.2830 | 0 | 4 |
| 120 | UNWEIGHTED | F2 | FIT | 0.9022 | undefined | 33.9623 | 0 | 3 |
| 120 | UNWEIGHTED | F3 | FIT | 0.8777 | undefined | 67.9245 | 0 | 6 |
| 120 | UNWEIGHTED | F4 | FIT | 0.8851 | undefined | 56.6038 | 0 | 5 |
| 120 | TRAIN_FOLD_CLASS_WEIGHT | F1 | FIT | 0.9047 | undefined | 45.2830 | 0 | 4 |
| 120 | TRAIN_FOLD_CLASS_WEIGHT | F2 | FIT | 0.9022 | undefined | 33.9623 | 0 | 3 |
| 120 | TRAIN_FOLD_CLASS_WEIGHT | F3 | FIT | 0.8777 | undefined | 22.6415 | 0 | 2 |
| 120 | TRAIN_FOLD_CLASS_WEIGHT | F4 | FIT | 0.8851 | undefined | 45.2830 | 0 | 4 |

### Aggregate AP and OOF status

| H (s) | method | aggregate status | mean AP | instability range | OOF |
|---:|---|---|---:|---:|---|
| 30 | B0_THRESHOLD | DEFINED | 0.4062 | 0.0013 | NOT_APPLICABLE |
| 30 | B1_HYSTERESIS | DEFINED | 0.3195 | 0.0544 | NOT_APPLICABLE |
| 30 | TRAIN_FOLD_CLASS_WEIGHT | DEFINED | 1.0000 | 0 | DEFINED |
| 30 | UNWEIGHTED | DEFINED | 1.0000 | 0 | DEFINED |
| 60 | B0_THRESHOLD | DEFINED | 0.9885 | 0.0017 | NOT_APPLICABLE |
| 60 | B1_HYSTERESIS | DEFINED | 0.6911 | 0.0113 | NOT_APPLICABLE |
| 60 | TRAIN_FOLD_CLASS_WEIGHT | DEFINED | 1.0000 | 0 | DEFINED |
| 60 | UNWEIGHTED | DEFINED | 1.0000 | 0 | DEFINED |
| 120 | B0_THRESHOLD | DEFINED | 0.8991 | 0.0839 | NOT_APPLICABLE |
| 120 | B1_HYSTERESIS | DEFINED | 0.8319 | 0.0038 | NOT_APPLICABLE |
| 120 | TRAIN_FOLD_CLASS_WEIGHT | DEFINED | 0.8924 | 0.0270 | DEFINED |
| 120 | UNWEIGHTED | DEFINED | 0.8924 | 0.0270 | DEFINED |

Undefined AP carries its reason (single-class fold/population); no value is imputed. EWT and AIW are NOT_ESTIMABLE for every horizon: EWT `EWT_UNAVAILABLE_NO_QUALIFIED_COMMON_TRAJECTORY`, AIW `AIW_UNAVAILABLE_MEASURED_LATENCY_CHAIN_MISSING`.

### Real physical population — refusal rows

Every horizon carries a REAL_REFUSAL row in horizon-metrics.csv with all metrics null/NOT_ESTIMABLE and the Phase A refusal reasons; no real prevalence, AP, event recall, false-warning rate, EWT or AIW is fabricated.

### Limitations

- synthetic development population only; no real physical run is eligible for the predictive dataset under the W04 ladder
- the synthetic data-generating process does not approximate the six-litre plant; AP values are software controls
- EWT and AIW are NOT_ESTIMABLE: no measured non-overlapping latency chain and no eligible non-intervened real pair exist
- censored horizons are excluded, never labeled negative
- the locked synthetic test pair and any locked physical test partition remain untouched
- a horizon whose label configuration leaves a run with zero evaluable anchors is recorded as NOT_ESTIMABLE because the shared W11 grouped benchmark refuses that declared population (DEV_RUN_WITHOUT_EVALUABLE_ANCHORS) rather than drop the run; the W11 repair is verified by the W13 regression, not reimplemented here

## Replay

```bash
git archive d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85 evidence/A/SOURCES/20261107/datasets \
    | tar -x -C <export-dir>
cd ml
python scripts/horizon-study-W13.py \
    --a-dataset-dir <export-dir>/evidence/A/SOURCES/20261107/datasets \
    --out reports/W13 --repository-revision <stack-head>
```

All consumed evidence bytes are SHA-256 pinned in horizon-manifest-W13.json; any mismatch refuses the run (exit 2). Model artifacts are written to a scratch directory and hash-recorded, never committed.
