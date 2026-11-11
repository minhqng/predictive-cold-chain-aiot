# Predictive eligibility review — existing physical sources

> This review answers the eight admission questions for every exported source. A descriptive use and a predictive refusal are both valid outcomes; they are kept in separate columns and statuses.

```text
EXPLORATORY_PREDICTIVE_ASSESSMENT = NOT_ESTIMABLE
REAL_PREDICTIVE_BENCHMARK = NOT_ESTABLISHED
AP / EVENT_RECALL / FORECAST_ACCURACY = NOT_ESTIMABLE
GATE_B_PHYSICAL_DATA = RED
PREDICTIVE_DATASET_READINESS = NOT_READY
```

## 1. Eight-question matrix

| source | Q1 physical | Q2 mapping | Q3 time | Q4 event | Q5 label | Q6 independence | Q7 causal features | Q8 suitable use |
|---|---|---|---|---|---|---|---|---|
| A20261107:W10-02 | YES | YES | NO | YES | NO | NO | NO | NEITHER |
| A20261107:W10-03-run1 | YES | YES | NO | YES | NO | NO | NO | NEITHER |
| A20261107:W10-03-run2 | YES | YES | NO | YES | NO | NO | NO | NEITHER |
| A20261107:W10-03-run3 | YES | YES | NO | YES | NO | NO | NO | NEITHER |
| A20261107:W10-03-run4 | YES | YES | NO | YES | NO | NO | NO | NEITHER |
| A20261107:S2-20261107-between-window | YES | YES | NO | NO | NO | NO | NO | NEITHER |
| A20261107:trial2 | YES | YES | NO | NO | NO | NO | NO | NEITHER |
| A20261107:trial3 | YES | YES | NO | NO | NO | NO | NO | NEITHER |
| A20261107:trial4 | YES | YES | NO | NO | NO | NO | NO | NEITHER |
| A20261107:S1-20261107-between-window | YES | YES | NO | NO | NO | NO | NO | NEITHER |
| A20261107:trial1-imported | YES | YES | NO | NO | NO | NO | NO | NEITHER |
| A20261107:H8-C-600s-TEC-100pct | YES | YES | NO | NO | NO | NO | NO | NEITHER |
| A20261107:H8-E-1800s-TEC-100pct | YES | YES | NO | NO | NO | NO | NO | NEITHER |
| A20261107:a-w07-02-run-1-4b555191 | YES | PARTIAL | NO | NO | NO | NO | NO | NEITHER |
| A20261107:a-w07-02-run-2-4b555191 | YES | PARTIAL | NO | NO | NO | NO | NO | NEITHER |
| A20261107:a-w07-02-run-3-4b555191 | YES | PARTIAL | NO | NO | NO | NO | NO | NEITHER |
| A20261107:a-w07-03-trial-2-be89bf4a | YES | YES | NO | NO | NO | NO | NO | NEITHER |
| A20261107:a-w07-03-trial-3-f44c9bed | YES | YES | NO | NO | NO | NO | NO | NEITHER |

## 2. Why predictive metrics are not estimable

- No frozen critical Tmean threshold and no representative T, so no critical-event label can be defined without inventing one.
- No device wall clock, no clock synchronization evidence and no physical event UTC. Host receipt time is not event time.
- The 18 rows/segments span 8 boots; repeated windows in one boot are not independent runs. There is no independent held-out source group.
- The five S2 door events are real and recorded, but they all belong to one boot. A door-event exploratory model would have five events in one session and no independent test group; AP and event recall remain undefined.
- S1 windows are passive baselines with no event labels.
- No source is assigned `EXPLORATORY_MODEL_INPUT_CANDIDATE` or `PREDICTIVE_ADMISSION_VERIFIED`: the five S2 door events share one session, the S1 windows have no event labels, and the critical threshold is unfrozen. A descriptive demonstration is still useful, but an exploratory predictive check is not estimable.

Refusal reasons (exact):

```text
EVENT_UTC_NOT_EVIDENCED
CALIBRATION_TRACEABILITY_ABSENT
RUN_IDENTITY_UNRESOLVED
SEGMENTS_SHARE_BOOTS_ROWS_ARE_NOT_INDEPENDENT_RUNS
CRITICAL_THRESHOLD_AND_REPRESENTATIVE_T_NOT_FROZEN
NO_VALID_CRITICAL_EVENT_LABEL
```

Exploratory reasons:

```text
NO_FROZEN_LABEL
NO_INDEPENDENT_HELD_OUT_SOURCE_GROUP
NO_PHYSICAL_EVENT_TIME
FIVE_S2_DOOR_EVENTS_IN_ONE_BOOT_ONLY
S1_WINDOWS_ARE_PASSIVE_WITH_NO_EVENT_LABELS
```

## 3. W15 synthetic model

```text
W15_SCORING = SKIPPED_FEATURE_INPUT_INCOMPLETE
MODEL_EVIDENCE_CLASS = SYNTHETIC_SOFTWARE_CONTROL_ONLY
MODEL_RELEASE = NON_DEPLOYABLE_CANDIDATE
MODEL_SCORE_SEMANTICS = RISK_SCORE_ONLY
W15_ARTIFACT_BYTES = NOT_MODIFIED
```

Missing feature inputs (exact):

```text
frozen_target_label
critical_tmean_threshold
event_time_utc
calibration_id
time_since_open_for_S1
ambient_temperature_c_for_S1_S2
relative_humidity_pct_for_S1_S2
```

A risk score is not a calibrated probability. No W15 inference is executed because the feature input is incomplete and the model is synthetic and non-deployable. Missing real features are not forced into the model.

## 4. Boundary checks

- The W05 export/row-validity/raw trio is a packaging alias of the H8-C segment already in the matrix; it is not an additional predictive candidate.
- W21 is `ON_DEVICE_SOFTWARE_INJECTION`, not a physical predictive candidate; its diagnostic counts are reported separately.
- W16 locked-test values: **NOT_OPENED**.
- W20 final physical A/B outcomes: **NOT_RUN**.
- No random row-level split and no overlapping train/test source lineage is used; the predictive path is refused before a split.
- No label is fabricated from an unfrozen threshold; no synthetic metric is promoted to physical evidence.

## 5. Gate B is separate

The canonical Gate B verdict remains **RED** / **NOT_READY**. The descriptive recovery status does not change it.

