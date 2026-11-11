# Existing physical data assessment — Member B

> Recovery package for bounded descriptive use of the physical data already in the repository. No new measurement, no model training, no Gate B override and no physical command path.

```text
EXISTING_PHYSICAL_DATA_AUDIT:
COMPLETE
USABLE_PHYSICAL_DESCRIPTIVE_DATA:
VERIFIED
USABLE_DOOR_DISTURBANCE_DATA:
VERIFIED
USABLE_SENSOR_DIAGNOSTIC_DATA:
PARTIAL
EXPLORATORY_PREDICTIVE_ASSESSMENT:
NOT_ESTIMABLE
REAL_PREDICTIVE_BENCHMARK:
NOT_ESTABLISHED
GATE_B_PHYSICAL_DATA:
RED
PREDICTIVE_DATASET_READINESS:
NOT_READY
EXISTING_DATA_REUSE:
READY_FOR_BOUNDED_ANALYSIS
DEADLINE_DEMO_PACKAGE:
READY
W16_LOCKED_TEST:
NOT_OPENED
W20_PHYSICAL_AB_ANALYSIS:
NOT_RUN
```

## 1. Scope and method

- Sources are consumed only through the explicit allowlist in `source-inventory.json`; no repository-wide glob is used.
- The 18-row A package is exported read-only from the pinned main revision `d22c8d5b1fb3c05d8a9732ed0087d8e76b9f9e85`; its manifest and run index are SHA-256 verified before any row is read.
- Temperatures use T1=CHAMBER_CENTER, T3=CHAMBER_BOTTOM and T4=CHAMBER_NEAR_DOOR for chamber air; T2=TEC_HOT_SIDE is kept separate and never enters chamber-air means or spreads.
- Missing and invalid measurements stay missing; no value is replaced by zero to make a plot continuous.
- Time is boot-scoped device uptime. Host receipt stamps are not physical event time and are labelled as such.

### Row-quality caveat

The A-normalized S1/S2 rows carry a legacy combined `quality` token (`INVALID` on every row) while A's independent `quality_report.md` reports 120/120 and 300/300 thermal OK for the S2 windows, 600/600–601/601 for S1 trials 2–4, 599/600 thermal and 598/600 electrical for trial1-imported, and 0 door-unverified on the accepted S2 windows. Trial1-imported and the outside windows carry one unknown door frame. The analysis therefore uses the per-channel `*_status` fields, discloses the row token, and never zero-fills. For H8-C, the W05 source excludes 17 startup frames whose snapshot is `INVALID`; the A-normalized segment includes them, but the reported cooling phase starts after frame 226 and is unaffected. One exact duplicate row in each W07 500-permille segment is deduplicated and counted; the exported row count remains 196.

## 2. Inventory summary

| source | scenario | boot | frames | A verdict | B use | verified disposition |
|---|---|---|---|---|---|---|
| A20261107:W10-02 | S2_TIMING | 73311d0c | 120 | DATASET_ACCEPTED_S2 | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_DISTURBANCE_ANALYSIS_USABLE | PHYSICAL_DISTURBANCE_ANALYSIS_USABLE |
| A20261107:W10-03-run1 | S2_DOOR | 73311d0c | 300 | DATASET_ACCEPTED_S2 | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_DISTURBANCE_ANALYSIS_USABLE | PHYSICAL_DISTURBANCE_ANALYSIS_USABLE |
| A20261107:W10-03-run2 | S2_DOOR | 73311d0c | 300 | DATASET_ACCEPTED_S2 | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_DISTURBANCE_ANALYSIS_USABLE | PHYSICAL_DISTURBANCE_ANALYSIS_USABLE |
| A20261107:W10-03-run3 | S2_DOOR | 73311d0c | 300 | DATASET_ACCEPTED_S2 | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_DISTURBANCE_ANALYSIS_USABLE | PHYSICAL_DISTURBANCE_ANALYSIS_USABLE |
| A20261107:W10-03-run4 | S2_DOOR | 73311d0c | 300 | DATASET_ACCEPTED_S2 | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_DISTURBANCE_ANALYSIS_USABLE | PHYSICAL_DISTURBANCE_ANALYSIS_USABLE |
| A20261107:S2-20261107-between-window | S2_OUTSIDE | 73311d0c | 346 | REAL_FRAMES_OUTSIDE_TIMED_WINDOWS | NOT_USABLE_FOR_REQUESTED_ANALYSIS | NOT_USABLE_FOR_REQUESTED_ANALYSIS |
| A20261107:trial2 | S1 | 4a21a645 | 600 | DATASET_ACCEPTED_S1 | PHYSICAL_DESCRIPTION_USABLE | PHYSICAL_DESCRIPTION_USABLE |
| A20261107:trial3 | S1 | 4a21a645 | 600 | DATASET_ACCEPTED_S1 | PHYSICAL_DESCRIPTION_USABLE | PHYSICAL_DESCRIPTION_USABLE |
| A20261107:trial4 | S1 | 4a21a645 | 601 | DATASET_ACCEPTED_S1 | PHYSICAL_DESCRIPTION_USABLE | PHYSICAL_DESCRIPTION_USABLE |
| A20261107:S1-20261107-between-window | S1_OUTSIDE | 4a21a645 | 62 | REAL_FRAMES_OUTSIDE_TIMED_WINDOWS | NOT_USABLE_FOR_REQUESTED_ANALYSIS | NOT_USABLE_FOR_REQUESTED_ANALYSIS |
| A20261107:trial1-imported | S1 | c20d17f6 | 600 | DATASET_ACCEPTED_S1 | PHYSICAL_DESCRIPTION_USABLE | PHYSICAL_DESCRIPTION_USABLE |
| A20261107:H8-C-600s-TEC-100pct | COOLING_STEP | 56044b74 | 957 | REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | PHYSICAL_DESCRIPTION_USABLE |
| A20261107:H8-E-1800s-TEC-100pct | COOLING_STEP_1800S | c4ff0ab3 | 2915 | REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | PHYSICAL_DESCRIPTION_USABLE |
| A20261107:a-w07-02-run-1-4b555191 | W07_PASSIVE_REPEAT | 4b555191 | 300 | REAL_PHYSICAL_REPEATS / INDEPENDENCE_CAVEAT | PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | PHYSICAL_SENSOR_DIAGNOSTIC_USABLE |
| A20261107:a-w07-02-run-2-4b555191 | W07_PASSIVE_REPEAT | 4b555191 | 300 | REAL_PHYSICAL_REPEATS / INDEPENDENCE_CAVEAT | PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | PHYSICAL_SENSOR_DIAGNOSTIC_USABLE |
| A20261107:a-w07-02-run-3-4b555191 | W07_PASSIVE_REPEAT | 4b555191 | 300 | REAL_PHYSICAL_REPEATS / INDEPENDENCE_CAVEAT | PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | PHYSICAL_SENSOR_DIAGNOSTIC_USABLE |
| A20261107:a-w07-03-trial-2-be89bf4a | COOLING_STEP_500PERMILLE | be89bf4a | 196 | REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | PHYSICAL_DESCRIPTION_USABLE |
| A20261107:a-w07-03-trial-3-f44c9bed | COOLING_STEP_500PERMILLE | f44c9bed | 196 | REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | PHYSICAL_DESCRIPTION_USABLE |

Family totals: **18 rows/segments**, **9293 frames**, **8 distinct boots**, **4 accepted S1 windows**, **5 accepted S2 windows**, **0 predictive-eligible runs**.

18 exported rows/segments span 8 distinct boots; rows and windows are never independent runs.

Packaging aliases and declared-but-unavailable sources:

| source | family | boot/session | frames | disposition | note |
|---|---|---|---|---|---|
| W05A:CG-S1-H8C-600S | W05_A_EXPORT | boot:56044b74 | 957 | PHYSICAL_DESCRIPTION_USABLE | row-validity CSV is the per-frame source for these values; the W05 export JSON (f6235e23...) is metadata and the W04 raw CSV (f8716b51...) is the raw capture; all three are one physical recording, same as A20261107:H8-C-600s-TEC-100pct, and are never counted twice |
| A-W21:02_03 | W21_ON_DEVICE | W21-02_W21-03_combined | 100 | PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | one boot and one raw log for two test IDs; the raw log is declared but absent from this checkout |
| A-W21:RAW_LOG | UNAVAILABLE |  |  | SOURCE_UNAVAILABLE | DECLARED_RAW_LOG_NOT_PRESENT_IN_CHECKOUT |
| PR95:SUPPLEMENT | UNAVAILABLE |  |  | UNMERGED_SUPPLEMENTARY_EVIDENCE | OPEN_UNMERGED_NOT_CONSUMED |

## 3. Source relationships

| boot | sources | independent sessions | note |
|---|---|---|---|
| 4a21a645 | A20261107:S1-20261107-between-window, A20261107:trial2, A20261107:trial3, A20261107:trial4 | 1 | multiple exported windows/segments share one boot; the boot is the independence ceiling, never the row |
| 4b555191 | A20261107:a-w07-02-run-1-4b555191, A20261107:a-w07-02-run-2-4b555191, A20261107:a-w07-02-run-3-4b555191 | 1 | multiple exported windows/segments share one boot; the boot is the independence ceiling, never the row |
| 56044b74 | A20261107:H8-C-600s-TEC-100pct, W05A:CG-S1-H8C-600S | 1 | multiple exported windows/segments share one boot; the boot is the independence ceiling, never the row |
| 73311d0c | A20261107:S2-20261107-between-window, A20261107:W10-02, A20261107:W10-03-run1, A20261107:W10-03-run2, A20261107:W10-03-run3, A20261107:W10-03-run4 | 1 | multiple exported windows/segments share one boot; the boot is the independence ceiling, never the row |

The W05 export/row-validity/raw trio is the same physical recording as the A H8-C segment (boot `56044b74`, 957 frames) and is never counted twice. PR #95 remains `UNMERGED_SUPPLEMENTARY_EVIDENCE` and is cited only.

## 4. Per-source rescued evidence

| source | physical measurement | permitted analysis | key calculated result | limitations |
|---|---|---|---|---|
| A20261107:W10-02 | T1/T3/T4 chamber air, T2 hot side, recorded door state | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_DISTURBANCE_ANALYSIS_USABLE | chamber air mean 29.8035 degC (min 29.7500, max 29.8958, change -0.0833); T2 hot side mean 29.7052 degC (max 29.7500); 1 recorded door event(s); durations 14.0 s | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=A_ROW_QUALITY_INVALID=120; door=RECORDED_TRANSITIONS_WITH_OPERATOR_COMMAND_LOG; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:W10-03-run1 | T1/T3/T4 chamber air, T2 hot side, recorded door state | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_DISTURBANCE_ANALYSIS_USABLE | chamber air mean 29.7952 degC (min 29.7292, max 29.8542, change 0.0000); T2 hot side mean 29.6962 degC (max 29.7500); 1 recorded door event(s); durations 12.9 s | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=A_ROW_QUALITY_INVALID=300; door=RECORDED_TRANSITIONS_WITH_OPERATOR_COMMAND_LOG; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:W10-03-run2 | T1/T3/T4 chamber air, T2 hot side, recorded door state | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_DISTURBANCE_ANALYSIS_USABLE | chamber air mean 29.8317 degC (min 29.7500, max 29.8958, change 0.0833); T2 hot side mean 29.7990 degC (max 29.8750); 1 recorded door event(s); durations 14.1 s | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=A_ROW_QUALITY_INVALID=300; door=RECORDED_TRANSITIONS_WITH_OPERATOR_COMMAND_LOG; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:W10-03-run3 | T1/T3/T4 chamber air, T2 hot side, recorded door state | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_DISTURBANCE_ANALYSIS_USABLE | chamber air mean 29.9157 degC (min 29.8542, max 29.9583, change 0.0208); T2 hot side mean 29.8631 degC (max 29.9375); 1 recorded door event(s); durations 14.1 s | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=A_ROW_QUALITY_INVALID=300; door=RECORDED_TRANSITIONS_WITH_OPERATOR_COMMAND_LOG; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:W10-03-run4 | T1/T3/T4 chamber air, T2 hot side, recorded door state | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_DISTURBANCE_ANALYSIS_USABLE | chamber air mean 29.9572 degC (min 29.8958, max 30.0000, change 0.0000); T2 hot side mean 29.8846 degC (max 29.9375); 1 recorded door event(s); durations 14.1 s | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=A_ROW_QUALITY_INVALID=300; door=RECORDED_TRANSITIONS_WITH_OPERATOR_COMMAND_LOG; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:S2-20261107-between-window | T1/T3/T4 chamber air, T2 hot side | NOT_USABLE_FOR_REQUESTED_ANALYSIS | chamber air mean 29.8748 degC (min 29.7708, max 29.9792, change 0.0833); T2 hot side mean 29.7736 degC (max 29.9375) | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=A_ROW_QUALITY_INVALID=346; DOOR_STATE_UNKNOWN=1; DOOR_STATUS_UNVERIFIED_PRESENT; door=RECORDED_UNVERIFIED_NO_EVENT; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:trial2 | T1/T3/T4 chamber air, T2 hot side | PHYSICAL_DESCRIPTION_USABLE | chamber air mean 29.8021 degC (min 29.7500, max 29.8542, change 0.0417); T2 hot side mean 29.7459 degC (max 29.7500) | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=A_ROW_QUALITY_INVALID=600; door=RECORDED_CLOSED_NO_EVENT; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:trial3 | T1/T3/T4 chamber air, T2 hot side | PHYSICAL_DESCRIPTION_USABLE | chamber air mean 29.8453 degC (min 29.8125, max 29.8750, change 0.0625); T2 hot side mean 29.7527 degC (max 29.8125) | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=A_ROW_QUALITY_INVALID=600; door=RECORDED_CLOSED_NO_EVENT; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:trial4 | T1/T3/T4 chamber air, T2 hot side | PHYSICAL_DESCRIPTION_USABLE | chamber air mean 29.8589 degC (min 29.8333, max 29.8750, change 0.0208); T2 hot side mean 29.7502 degC (max 29.8125) | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=A_ROW_QUALITY_INVALID=601; door=RECORDED_CLOSED_NO_EVENT; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:S1-20261107-between-window | T1/T3/T4 chamber air, T2 hot side | NOT_USABLE_FOR_REQUESTED_ANALYSIS | chamber air mean 29.7585 degC (min 29.7500, max 29.7917, change 0.0208); T2 hot side mean 29.7459 degC (max 29.7500) | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=A_ROW_QUALITY_INVALID=62; DOOR_STATE_UNKNOWN=1; DOOR_STATUS_UNVERIFIED_PRESENT; door=RECORDED_UNVERIFIED_NO_EVENT; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:trial1-imported | T1/T3/T4 chamber air, T2 hot side | PHYSICAL_DESCRIPTION_USABLE | chamber air mean 29.4624 degC (min 29.1250, max 29.7500, change 0.5417); T2 hot side mean 29.6952 degC (max 29.7500) | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=A_ROW_QUALITY_INVALID=600; DOOR_STATE_UNKNOWN=1; DOOR_STATUS_UNVERIFIED_PRESENT; door=RECORDED_UNVERIFIED_NO_EVENT; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:H8-C-600s-TEC-100pct | T1/T3/T4 chamber air, T2 hot side, PWM applied/current/power/energy | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | chamber air mean 25.1315 degC (min 21.3127, max 30.0417, change -3.2710); T2 hot side mean 35.4198 degC (max 39.9380); cooling phase: air change -8.7083 degC, T2 change 9.6870 degC | time=BOOT_SCOPED_UPTIME; run_id=SEGMENT_ONLY_NOT_AN_INDEPENDENT_RUN; calibration=NOT_AVAILABLE; quality=DOOR_STATE_UNKNOWN=17; DOOR_STATUS_UNVERIFIED_PRESENT; W05_RAW_ELECTRICAL_STATUS_ABSENT; SAME_RECORDING_AS_W05_ALIAS; door=RECORDED_UNVERIFIED_NO_EVENT; cooling=RECORDED_APPLIED_DUTY |
| A20261107:H8-E-1800s-TEC-100pct | T1/T3/T4 chamber air, T2 hot side, PWM applied/current/power/energy | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | chamber air mean 29.6860 degC (min 29.5833, max 29.7917, change -0.0417); T2 hot side mean 34.6465 degC (max 37.6880); cooling phase: air change 0.1037 degC, T2 change 7.7500 degC | time=BOOT_SCOPED_UPTIME; run_id=SEGMENT_ONLY_NOT_AN_INDEPENDENT_RUN; calibration=NOT_AVAILABLE; quality=DOOR_STATE_UNKNOWN=14; DOOR_STATUS_UNVERIFIED_PRESENT; door=RECORDED_UNVERIFIED_NO_EVENT; cooling=RECORDED_APPLIED_DUTY |
| A20261107:a-w07-02-run-1-4b555191 | compact capture: T1 slot and T2 slot only; T3/T4 absent | PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | T1-slot mean 30.1200 degC (not a chamber-air mean) | time=FRAME_INDEX_ONLY; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=DOOR_STATE_UNKNOWN=300; CURRENT_STATUS_NOT_CARRIED=300; DOOR_STATUS_NOT_CARRIED=300; door=RECORDED_UNVERIFIED_NO_EVENT; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:a-w07-02-run-2-4b555191 | compact capture: T1 slot and T2 slot only; T3/T4 absent | PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | T1-slot mean 30.1252 degC (not a chamber-air mean) | time=FRAME_INDEX_ONLY; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=DOOR_STATE_UNKNOWN=300; CURRENT_STATUS_NOT_CARRIED=300; DOOR_STATUS_NOT_CARRIED=300; door=RECORDED_UNVERIFIED_NO_EVENT; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:a-w07-02-run-3-4b555191 | compact capture: T1 slot and T2 slot only; T3/T4 absent | PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | T1-slot mean 30.1248 degC (not a chamber-air mean) | time=FRAME_INDEX_ONLY; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=DOOR_STATE_UNKNOWN=300; CURRENT_STATUS_NOT_CARRIED=300; DOOR_STATUS_NOT_CARRIED=300; door=RECORDED_UNVERIFIED_NO_EVENT; cooling=NO_COOLING_PHASE_RECORDED |
| A20261107:a-w07-03-trial-2-be89bf4a | T1/T3/T4 chamber air, T2 hot side, requested PWM (applied duty not carried), PZEM current/power/energy | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | chamber air mean 29.0266 degC (min 27.8333, max 30.1250, change -2.2708); T2 hot side mean 32.0936 degC (max 33.5625); cooling phase: air change -2.2500 degC, T2 change 3.6875 degC | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=DOOR_STATE_UNKNOWN=195; DOOR_STATUS_UNVERIFIED_PRESENT; EXACT_DUPLICATE_ROWS_DEDUPLICATED=1; PWM_APPLIED_NOT_CARRIED; door=RECORDED_UNVERIFIED_NO_EVENT; cooling=RECORDED_PZEM_CURRENT_ONLY |
| A20261107:a-w07-03-trial-3-f44c9bed | T1/T3/T4 chamber air, T2 hot side, requested PWM (applied duty not carried), PZEM current/power/energy | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | chamber air mean 28.9692 degC (min 27.7708, max 30.0625, change -2.2500); T2 hot side mean 32.0949 degC (max 33.6250); cooling phase: air change -2.2500 degC, T2 change 3.6875 degC | time=BOOT_SCOPED_UPTIME; run_id=UNSET_NOT_A_RUN_ID; calibration=NOT_AVAILABLE; quality=DOOR_STATE_UNKNOWN=195; DOOR_STATUS_UNVERIFIED_PRESENT; EXACT_DUPLICATE_ROWS_DEDUPLICATED=1; PWM_APPLIED_NOT_CARRIED; door=RECORDED_UNVERIFIED_NO_EVENT; cooling=RECORDED_PZEM_CURRENT_ONLY |
| W05A:CG-S1-H8C-600S | T1/T3/T4 chamber air, T2 hot side, PWM applied/current/power/energy | PHYSICAL_DESCRIPTION_USABLE, PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | chamber air mean 25.0449 degC (min 21.3127, max 30.0417, change -3.2710); T2 hot side mean 35.5201 degC (max 39.9380); cooling phase: air change -8.7083 degC, T2 change 9.6870 degC | time=BOOT_SCOPED_UPTIME; run_id=UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID; calibration=NOT_AVAILABLE; quality=AUTHORITY_A_LEDGER_INVALID; SNAPSHOT_INVALID=17; THERMALLY_USABLE=940; DOOR_STATE_UNKNOWN=957; ELECTRICAL_STATUS_NOT_CARRIED_IN_RAW; door=RECORDED_DOOR_STATE_UNKNOWN_NO_EVENT; cooling=RECORDED_APPLIED_DUTY |
| A-W21:02_03 | on-device software injection: 100 frames, one session, two test IDs; output stage compiled out | PHYSICAL_SENSOR_DIAGNOSTIC_USABLE | descriptive counts only | time=DEVICE_BOOT_SCOPED_NO_TIMESTAMPS; run_id=TWO_TEST_IDS_ONE_BOOT; calibration=NOT_AVAILABLE; quality=RAW_LOG_SOURCE_UNAVAILABLE; OUTPUT_STAGE_COMPILED_OUT; PZEM_MISSING_IN_FAULT_WINDOW; T1_INVALID_SOFTWARE_INJECTION; door=NOT_RECORDED; cooling=COMPILED_OUT |

## 5. Real descriptive results

Every quantitative row is in `real-observation-summary.csv` with its source path, SHA-256, calculation rule, frame count, independent run count and limitation. Representative values:

| quantity | value | unit | source | limitation |
|---|---|---|---|---|
| AIW | NOT_ESTIMABLE | s | A-W13:PLANT_TIMING | NOT_ESTIMABLE, never a zero |
| EWT | NOT_ESTIMABLE | s | A-W13:PLANT_TIMING | NOT_ESTIMABLE, never a zero |
| family_distinct_boots | 8 | boots | A20261107:DATASET | the boot is the independence ceiling |
| family_predictive_eligible_runs | 0 | runs | A20261107:DATASET | zero eligible predictive runs |
| chamber_air_max_c | 30.0417 | degC | A20261107:H8-C-600s-TEC-100pct | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_mean_c | 25.1315 | degC | A20261107:H8-C-600s-TEC-100pct | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_min_c | 21.3127 | degC | A20261107:H8-C-600s-TEC-100pct | T2 hot-side is never included; boot-scoped time, not absolute event time |
| cooling_phase_air_change_c | -8.7083 | degC | A20261107:H8-C-600s-TEC-100pct | PZEM measures the cooling branch, not the whole system; no missing value is zero-filled; source quality flags: DOOR_STATE_UNKNOWN=17; DOOR_STATUS_UNVERIFIED_PRESENT; W05_RAW_ELECTRICAL_STATUS_ABSENT; SAME_RECORDING_AS_W05_ALIAS |
| cooling_phase_t2_change_c | 9.6870 | degC | A20261107:H8-C-600s-TEC-100pct | PZEM measures the cooling branch, not the whole system; no missing value is zero-filled; source quality flags: DOOR_STATE_UNKNOWN=17; DOOR_STATUS_UNVERIFIED_PRESENT; W05_RAW_ELECTRICAL_STATUS_ABSENT; SAME_RECORDING_AS_W05_ALIAS |
| chamber_air_max_c | 29.7917 | degC | A20261107:H8-E-1800s-TEC-100pct | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_mean_c | 29.6860 | degC | A20261107:H8-E-1800s-TEC-100pct | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_min_c | 29.5833 | degC | A20261107:H8-E-1800s-TEC-100pct | T2 hot-side is never included; boot-scoped time, not absolute event time |
| cooling_phase_air_change_c | 0.1037 | degC | A20261107:H8-E-1800s-TEC-100pct | PZEM measures the cooling branch, not the whole system; no missing value is zero-filled; source quality flags: DOOR_STATE_UNKNOWN=14; DOOR_STATUS_UNVERIFIED_PRESENT |
| cooling_phase_t2_change_c | 7.7500 | degC | A20261107:H8-E-1800s-TEC-100pct | PZEM measures the cooling branch, not the whole system; no missing value is zero-filled; source quality flags: DOOR_STATE_UNKNOWN=14; DOOR_STATUS_UNVERIFIED_PRESENT |
| chamber_air_max_c | 29.7917 | degC | A20261107:S1-20261107-between-window | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_mean_c | 29.7585 | degC | A20261107:S1-20261107-between-window | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_min_c | 29.7500 | degC | A20261107:S1-20261107-between-window | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_max_c | 29.9792 | degC | A20261107:S2-20261107-between-window | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_mean_c | 29.8748 | degC | A20261107:S2-20261107-between-window | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_min_c | 29.7708 | degC | A20261107:S2-20261107-between-window | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_max_c | 29.8958 | degC | A20261107:W10-02 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_mean_c | 29.8035 | degC | A20261107:W10-02 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_min_c | 29.7500 | degC | A20261107:W10-02 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| door_event_1_during_minus_pre_c | -0.0169 | degC | A20261107:W10-02 | door is the recorded reported state; no absolute event time; no critical crossing is inferred |
| chamber_air_max_c | 29.8542 | degC | A20261107:W10-03-run1 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_mean_c | 29.7952 | degC | A20261107:W10-03-run1 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_min_c | 29.7292 | degC | A20261107:W10-03-run1 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| door_event_1_during_minus_pre_c | 0.0038 | degC | A20261107:W10-03-run1 | door is the recorded reported state; no absolute event time; no critical crossing is inferred |
| chamber_air_max_c | 29.8958 | degC | A20261107:W10-03-run2 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_mean_c | 29.8317 | degC | A20261107:W10-03-run2 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_min_c | 29.7500 | degC | A20261107:W10-03-run2 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| door_event_1_during_minus_pre_c | -0.0005 | degC | A20261107:W10-03-run2 | door is the recorded reported state; no absolute event time; no critical crossing is inferred |
| chamber_air_max_c | 29.9583 | degC | A20261107:W10-03-run3 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_mean_c | 29.9157 | degC | A20261107:W10-03-run3 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| chamber_air_min_c | 29.8542 | degC | A20261107:W10-03-run3 | T2 hot-side is never included; boot-scoped time, not absolute event time |
| door_event_1_during_minus_pre_c | 0.0011 | degC | A20261107:W10-03-run3 | door is the recorded reported state; no absolute event time; no critical crossing is inferred |

## 6. Plots

All plots declare `PHYSICAL_RECORDED_DATA`, source ID, revision, source SHA-256, scenario, boot/run identity, units and the measurement/time-domain limitations. T2 is always a separate panel or series. Gaps are missing data, never zero.

| plot | source identity | declared evidence |
|---|---|---|
| chamber-air-a20261107-trial2.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |
| chamber-air-a20261107-w10-03-run1.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |
| cooling-a20261107-a-w07-03-trial-2-be89bf4a.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |
| cooling-a20261107-h8-c-600s-tec-100pct.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |
| cooling-a20261107-h8-e-1800s-tec-100pct.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |
| door-a20261107-w10-02.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |
| door-a20261107-w10-03-run1.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |
| door-a20261107-w10-03-run2.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |
| door-a20261107-w10-03-run3.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |
| door-a20261107-w10-03-run4.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |
| missingness-inventory.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |
| w05-diagnostic.svg | see SVG subtitle/footer | PHYSICAL_RECORDED_DATA |

W21 has no frame-level plot: the declared raw log is not present in this checkout. Its bounded counts are reported in the CSV instead; no time series is invented.

## 7. What this supports and what it does not

- Supports: S1 passive temperature description; S2 recorded door state and thermal response description; cooling-branch observations for H8-C, H8-E and two W07 500-permille trials; T1-slot/T2 continuity for the W07 compact repeats; bounded W21 diagnostic counts.
- Does not support: predictive training or AP/event-recall/forecast claims; EWT/AIW; physical model performance; a critical-threshold crossing; a full-system power claim; a calibrated temperature claim.
- Gate B remains the authoritative verdict: `RED` / `NOT_READY`. `EXISTING_DATA_REUSE` and `DEADLINE_DEMO_PACKAGE` are delivery statuses, not Gate B.

