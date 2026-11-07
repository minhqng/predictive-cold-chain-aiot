# ColdGuard W07 — Physical baseline EDA, repeatability and pairing inputs

> Member B · W07 (B-W07-01 … B-W07-04). Source-based analysis only: no physical action, no model training, no W08 validator, no predictive dataset and no Controller A/B result.

## 0. Scientific separation

| Status | Value | Meaning |
|---|---|---|
| W07 SOFTWARE | GREEN | CLI completed, tests passed, artifacts deterministic |
| PHYSICAL REPEATABILITY | NOT_ESTABLISHED | qualified independent physical runs: 0 |
| PREDICTIVE DATASET | NOT_READY | W04 admission verdict is authoritative |
| REAL AIW | NOT_ESTIMABLE | W07 does not compute AIW |

A software-green W07 with absent physical repeats is an acceptable engineering
result. It is not a repeatability or performance claim.

## 1. Provenance and admission

| Field | Value |
|---|---|
| Report schema | `coldguard-w07-plant-eda-report-v1` |
| W07 layer version | `coldguard-w07-plant-eda-v1` |
| Analysis code SHA-256 | `29d74012516f89019be89bac935e6010ee012b6b7a61426a9b07b3154939b795` |
| Repository revision | `3f1829ab52d431262047707040f61f6f276dea51` |
| Source path | `evidence/A/W09/exports/CG-S1-H8C-600S.json` |
| Source SHA-256 | `f6235e23b4513f98ba7c1deb289f4a3d48afd3c0a87d7f38bfe4e67b2fc79feb` |
| Source namespace/format | `w09-run-export/v2` / `a-w09-run-export-v2` |
| Source provenance | `PHYSICAL` |
| Admission status | `EXCLUDED_OR_BLOCKED` |
| Highest admission stage | `USABLE_FOR_DIAGNOSTIC_QA` |
| Predictive dataset readiness | `NOT_READY` |
| Eligible S1 / S2 runs | `0` / `0` |
| Run identity | `run_id=None` (`UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID`); `run_ids=['run-00000000', 'run-00000001']` |
| Boot identity | `'56044b74'` (`SOURCE_CARRIED_SINGLE`) |
| Device identity | `None` (`NOT_CARRIED_BY_THIS_ENCODING`) |
| Hardware configuration | `'CG-HW-001'` (`DECLARED_NOT_VERIFIED`) |
| Calibration identity | `None` (`NOT_AVAILABLE`) |
| Scenario identity | `'S1'` (`CANDIDATE_NOT_CERTIFIED`) |
| Generation command | `python scripts/plant-eda-W07.py --source ../evidence/A/W09/exports/CG-S1-H8C-600S.json --a-run-index ../evidence/A/W09/s1-run-index.json --a-w07-dir ../evidence/A/W07 --out reports/W07 --representation tmean_airroles_v0 --trailing-samples 120 --temperature-change-thresholds 1.0,2.0 --min-runs 3 --percentile-method linear --repository-revision 3f1829ab52d431262047707040f61f6f276dea51` |

W06 timing/identity diagnostics consumed read-only:

| W06 diagnostic | Value |
|---|---|
| Event ordering | `ORDERED_IN_DOMAIN` |
| Order reason codes | `none` |
| Events / identity statuses | `959` / `{'PARTIAL': 959}` |
| Duplicate deliveries | `0` |
| Contradictory identities | `0` |
| Missing-identity events | `0` |
| Reboot identity resets | `0` |

W04 admission blockers:

- `A_LEDGER_INVALID` (PHYSICALLY_QUALIFIED) — A's authoritative validity ledger excludes this run: run_id_status=UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID: source run_id segments ['run-00000000', 'run-00000001'] under one boot_id are not independent runs and no joined run_id exists in the source, so none can be published for a join; majority of frames unusable
- `RUN_ID_UNRESOLVED` (PHYSICALLY_QUALIFIED) — run identity status 'UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID' is not a single source-carried run; no run_id is fabricated for a dataset join
- `DEVICE_IDENTITY_UNAVAILABLE` (PHYSICALLY_QUALIFIED) — device identity status 'NOT_CARRIED_BY_THIS_ENCODING'; cross-device identity cannot be asserted
- `HARDWARE_CONFIG_UNVERIFIED` (PHYSICALLY_QUALIFIED) — hardware configuration 'CG-HW-001' is a declared label; no verification evidence was supplied
- `CALIBRATION_IDENTITY_MISSING` (PHYSICALLY_QUALIFIED) — no calibration identity exists; a calibration id is never invented
- `PHYSICALLY_QUALIFIED_REQUIRED` (ELIGIBLE_FOR_PREDICTIVE_DATASET) — predictive admission requires the physically-qualified stage
- `SCENARIO_POPULATION_INELIGIBLE` (ELIGIBLE_FOR_PREDICTIVE_DATASET) — scenario 'S1' has no eligible rows under A's validity summary
- `TIME_DOMAIN_INSUFFICIENT_FOR_PREDICTIVE_DATASET` (ELIGIBLE_FOR_PREDICTIVE_DATASET) — time domain 'BOOT_SCOPED_UPTIME' / sync 'NOT_EVIDENCED' cannot support predictive event-time labels and EWT; boot-relative data stays diagnostic-only in W04

## 2. Evidence inventory and independence

| Item | Value |
|---|---|
| Rows | 957 |
| Boot sessions | 1 |
| Source run-id labels | 2 (run-00000000, run-00000001) |
| Source run labels create independent runs? | NO — one boot session |
| Phase segments | 3 |
| Undetermined phase rows | 0 |
| Independent physical sources | 1 |
| Qualified independent runs | 0 |
| Diagnostic phase records | 3 |
| Duplicate source views | 0 |
| Conflicting physical sources | 0 |

The 2 raw `run_id` label(s) are segments inside one boot. They do not establish independent runs, and the phase segments inside that boot do not establish experimental repetitions.

## 3. Temperature representations and physical roles

| Representation | Kind | Slots | Physical roles | Includes hot side | Available |
|---|---|---|---|---|---|
| `tmean_airroles_v0` | CHAMBER_AIR | t1, t3, t4 | CHAMBER_CENTER, CHAMBER_BOTTOM, CHAMBER_NEAR_DOOR | no | yes |
| `tmean_all4_v0` | SENSITIVITY | t1, t2, t3, t4 | CHAMBER_CENTER, TEC_HOT_SIDE, CHAMBER_BOTTOM, CHAMBER_NEAR_DOOR | YES | yes |
| `tmean_chamber3_v0` | CANONICAL_LITERAL_NON_AIR | t1, t2, t3 | CHAMBER_CENTER, TEC_HOT_SIDE, CHAMBER_BOTTOM | YES | yes |
| `tmean_t2excluded_v0` | CHAMBER_AIR | t1, t3 | CHAMBER_CENTER, CHAMBER_BOTTOM | no | yes |

Primary diagnostic representation: `tmean_airroles_v0` = mean of the role-qualified chamber-air probes.
`tmean_chamber3_v0` is the literal docs/01 §20.1 slot expression and averages T2 hot-side metal into an air temperature on this hardware. It is published only as a named non-air cross-check, never as chamber air.

## 4. Phase segmentation

| Phase | Index | Rows | Start (s) | End (s) | Run ids | Independent experiment | Reasons |
|---|---|---|---|---|---|---|---|
| PASSIVE_WARMUP | 0 | 226 | 0.904 | 225.894 | run-00000000 | NO | SAME_BOOT_PHASE_SEGMENT_IS_NOT_AN_INDEPENDENT_RUN |
| COOLING_STEP | 1 | 600 | 226.894 | 825.894 | run-00000001 | NO | REQUESTED_DUTY_DIFFERS_FROM_APPLIED, SAME_BOOT_PHASE_SEGMENT_IS_NOT_AN_INDEPENDENT_RUN |
| POST_ACTION_RECOVERY | 2 | 131 | 826.894 | 956.894 | run-00000001 | NO | APPLIED_LABEL_NOT_CARRIED, SAME_BOOT_PHASE_SEGMENT_IS_NOT_AN_INDEPENDENT_RUN |

Boundaries come from the applied-duty state (with the device-reported
applied label as a consistency check), not from filenames, desired
commands or ACKs. A missing applied state would be `UNDETERMINED` and
would join no phase; it is never converted to OFF.

## 5. Phase metrics

All temperatures are °C, slopes °C/min, power W, energy Wh. Time is
boot-relative `device_ms`; no cross-boot alignment and no interpolation
across missing or untrusted windows.

| Metric | PASSIVE_WARMUP | COOLING_STEP | POST_ACTION_RECOVERY |
|---|---|---|---|
| `start_c` | 29.916667 | 30.021000 | 21.312667 |
| `end_c` | 30.000000 | 21.312667 | 26.645667 |
| `delta_c` | 0.083333 | -8.708333 | 5.333000 |
| `min_c` | 29.916667 | 21.312667 | 21.312667 |
| `max_c` | 30.041667 | 30.041667 | 26.645667 |
| `whole_phase_slope_c_per_min` | 0.027185 | -0.854771 | 2.893160 |
| `trailing_slope_c_per_min` | 0.020463 | -0.070104 | 3.097228 |
| `minutes_to_1c` | NOT_ESTIMABLE | 0.850000 | 0.816667 |
| `minutes_to_2c` | NOT_ESTIMABLE | 1.250000 | 1.083333 |
| `initial_spread_c` | 0.374000 | 0.438000 | 0.750000 |
| `spread_median_c` | 0.375000 | 0.875000 | 0.563000 |
| `duration_min` | 3.749833 | 9.983333 | 2.166667 |
| `mean_power_w` | 0.000000 | 85.159333 | 0.708397 |
| `peak_power_w` | 0.000000 | 117.400000 | 84.200000 |
| `sampled_energy_wh` | 0.000000 | 14.169833 | 0.025778 |
| `counter_delta_wh` | 0.000000 | 14.000000 | 0.000000 |
| `valid_sample_fraction` | 1.000000 | 1.000000 | 1.000000 |

Quartiles and percentiles use the configured method (`linear` by default,
linear interpolation between closest ranks; `nearest_rank` is the alternative).

Additional per-phase facts:

| Fact | PASSIVE_WARMUP | COOLING_STEP | POST_ACTION_RECOVERY |
|---|---|---|---|
| `rows` | 226 | 600 | 131 |
| `usable_rows` | 226 | 600 | 131 |
| `skipped_rows` | 0 | 0 | 0 |
| `quality_valid_rows` | 226 | 600 | 131 |
| `quality_unqualified_rows` | 0 | 0 | 0 |
| `overall_quality_invalid_rows` | 17 | 0 | 0 |
| `initial_probes_c` | t1=30.000000, t3=29.688000, t4=30.062000 | t1=30.125000, t3=29.750000, t4=30.188000 | t1=20.875000, t3=21.625000, t4=21.438000 |
| `end_probes_c` | t1=30.125000, t3=29.750000, t4=30.125000 | t1=20.875000, t3=21.625000, t4=21.438000 | t1=26.750000, t3=26.312000, t4=26.875000 |
| `amplitude_direction` | WARMING | COOLING | WARMING |
| `representation` | `tmean_airroles_v0` | `tmean_airroles_v0` | `tmean_airroles_v0` |
| `trailing_slope_definition` | `tmean_airroles_v0/120samples/trailing_window_least_squares_v0` | `tmean_airroles_v0/120samples/trailing_window_least_squares_v0` | `tmean_airroles_v0/120samples/trailing_window_least_squares_v0` |
| `ambient_first_c` | 30.572000 | 30.658000 | 22.896000 |
| `ambient_mean_c` | 30.631903 | 24.495658 | 25.423252 |
| `ambient_min_c` | 30.572000 | 22.906000 | 22.890000 |
| `ambient_max_c` | 30.668000 | 30.663000 | 28.107000 |
| `rh_first_pct` | 68.915000 | 68.586000 | 58.605000 |
| `rh_mean_pct` | 68.731673 | 56.328145 | 81.576664 |
| `cooling_on_rows` | 0 | 600 | 0 |
| `applied_duty_min_permille` | 0 | 999 | 0 |
| `applied_duty_max_permille` | 0 | 999 | 0 |
| `applied_duty_mean_permille` | 0.000000 | 999.000000 | 0.000000 |
| `requested_mismatch_rows` | 0 | 600 | 0 |
| `cadence_median_s` | 1.000000 | 1.000000 | 1.000000 |
| `cadence_p95_s` | 1.000000 | 1.000000 | 1.000000 |
| `long_gap_count` | 0 | 0 | 0 |
| `electrical_qualification` | UNQUALIFIED | UNQUALIFIED | UNQUALIFIED |
| `environment_qualification` | UNQUALIFIED | UNQUALIFIED | UNQUALIFIED |
| `censoring` | NOT_CENSORED | NOT_CENSORED | CENSORED_AT_CAPTURE_END |
| `qualification` | DIAGNOSTIC_ONLY | DIAGNOSTIC_ONLY | DIAGNOSTIC_ONLY |

Slope discipline: the trailing-window slope is a separate diagnostic and
is not a phase summary. On the cooling step the trailing slope
(-0.070104 °C/min) differs from the whole-phase slope (-0.854771 °C/min).

## 6. External cross-check against A's W07 references

| Phase | Field | A reference | B computed | Unit | Status | Detail |
|---|---|---|---|---|---|---|
| PASSIVE_WARMUP | `start_c` | 29.916700 | 29.916667 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| PASSIVE_WARMUP | `end_c` | 30.000000 | 30.000000 | °C | MATCH | absolute difference 0 within 0.0005 |
| PASSIVE_WARMUP | `delta_c` | 0.083300 | 0.083333 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| PASSIVE_WARMUP | `max_c` | 30.041700 | 30.041667 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| PASSIVE_WARMUP | `min_c` | 29.916700 | 29.916667 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| PASSIVE_WARMUP | `whole_phase_slope_c_per_min` | 0.027185 | 0.027185 | °C/min | MATCH | absolute difference 0 within 1e-05 |
| PASSIVE_WARMUP | `slope_c_per_min` | 0.020463 | 0.020463 | °C/min | MATCH | absolute difference 0 within 1e-05 |
| PASSIVE_WARMUP | `minutes_to_1c` | NOT_ESTIMABLE | NOT_ESTIMABLE | min | MATCH | both absent |
| PASSIVE_WARMUP | `minutes_to_2c` | NOT_ESTIMABLE | NOT_ESTIMABLE | min | MATCH | both absent |
| PASSIVE_WARMUP | `samples` | 226 | 226 | rows | MATCH | absolute difference 0 within 0.5 |
| PASSIVE_WARMUP | `rows_read` | 226 | 226 | rows | MATCH | absolute difference 0 within 0.5 |
| COOLING_STEP | `start_c` | 30.021000 | 30.021000 | °C | MATCH | absolute difference 0 within 0.0005 |
| COOLING_STEP | `end_c` | 21.312700 | 21.312667 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| COOLING_STEP | `delta_c` | -8.708300 | -8.708333 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| COOLING_STEP | `max_c` | 30.041700 | 30.041667 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| COOLING_STEP | `min_c` | 21.312700 | 21.312667 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| COOLING_STEP | `whole_phase_slope_c_per_min` | -0.854771 | -0.854771 | °C/min | MATCH | absolute difference 0 within 1e-05 |
| COOLING_STEP | `slope_c_per_min` | -0.070104 | -0.070104 | °C/min | MATCH | absolute difference 0 within 1e-05 |
| COOLING_STEP | `minutes_to_1c` | 0.850000 | 0.850000 | min | MATCH | absolute difference 0 within 0.0005 |
| COOLING_STEP | `minutes_to_2c` | 1.250000 | 1.250000 | min | MATCH | absolute difference 0 within 0.0005 |
| COOLING_STEP | `samples` | 600 | 600 | rows | MATCH | absolute difference 0 within 0.5 |
| COOLING_STEP | `rows_read` | 600 | 600 | rows | MATCH | absolute difference 0 within 0.5 |
| POST_ACTION_RECOVERY | `start_c` | 21.312700 | 21.312667 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| POST_ACTION_RECOVERY | `end_c` | 26.645700 | 26.645667 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| POST_ACTION_RECOVERY | `delta_c` | 5.333000 | 5.333000 | °C | MATCH | absolute difference 0 within 0.0005 |
| POST_ACTION_RECOVERY | `max_c` | 26.645700 | 26.645667 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| POST_ACTION_RECOVERY | `min_c` | 21.312700 | 21.312667 | °C | MATCH | absolute difference 3.3e-05 within 0.0005 |
| POST_ACTION_RECOVERY | `whole_phase_slope_c_per_min` | 2.893160 | 2.893160 | °C/min | MATCH | absolute difference 0 within 1e-05 |
| POST_ACTION_RECOVERY | `slope_c_per_min` | 3.097228 | 3.097228 | °C/min | MATCH | absolute difference 0 within 1e-05 |
| POST_ACTION_RECOVERY | `minutes_to_1c` | 0.816700 | 0.816667 | min | MATCH | absolute difference 3.3e-05 within 0.0005 |
| POST_ACTION_RECOVERY | `minutes_to_2c` | 1.083300 | 1.083333 | min | MATCH | absolute difference 3.3e-05 within 0.0005 |
| POST_ACTION_RECOVERY | `samples` | 131 | 131 | rows | MATCH | absolute difference 0 within 0.5 |
| POST_ACTION_RECOVERY | `rows_read` | 131 | 131 | rows | MATCH | absolute difference 0 within 0.5 |

A's numbers are external read-only cross-check targets; B's values
above are independently computed from the W04 normalized capture.

## 7. Electrical diagnostics and source anomaly

Electrical qualification is **UNQUALIFIED** in this capture: no electrical column carries a recorded OK. Numeric electrical summaries are diagnostic-only. No qualified energy envelope, COP or whole-system power claim is made. An OFF command is not proof of measured zero current.

| Phase | Mean current A | Peak current A | Mean power W | Peak power W | Sampled energy Wh (diagnostic) | Counter delta Wh (diagnostic) |
|---|---|---|---|---|---|---|
| PASSIVE_WARMUP | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| COOLING_STEP | 7.224683 | 9.990000 | 85.159333 | 117.400000 | 14.169833 | 14.000000 |
| POST_ACTION_RECOVERY | 0.060382 | 7.150000 | 0.708397 | 84.200000 | 0.025778 | 0.000000 |

Source anomaly retained (not averaged away):

- `device_ms=826894` seq 827: applied state `OFF` with duty 0 permille, yet 7.150000 A / 84.200000 W. Classification: `CANDIDATE_CONTROL_ELECTRICAL_ANOMALY_NOT_RESOLVED_BY_HOST_TOOL`. Competing explanation: PZEM register/transition lag is possible; the trace decays toward zero after this frame, but a meter trace is not a verified zero-current measurement. Resolution: kept visible with provenance; no independent conclusion that the power stage was energized; no averaging or deletion.

## 8. Repeatability

**Verdict: `NOT_ESTABLISHED`**

| Field | Value |
|---|---|
| Minimum independent runs (A-W07) | 3 |
| Independent physical sources | 1 |
| Qualified independent runs | 0 |
| Excluded records | 3 |
| Duplicate source views | 0 |
| Conflicting physical sources | 0 |
| Reason codes | ADMISSION_NOT_PHYSICALLY_QUALIFIED, A_LEDGER_NOT_VALID, CALIBRATION_IDENTITY_MISSING, DEVICE_IDENTITY_MISSING, HARDWARE_CONFIG_NOT_VERIFIED, MINIMUM_INDEPENDENT_RUNS_NOT_MET, NO_QUALIFIED_INDEPENDENT_RUNS, RUN_IDENTITY_UNRESOLVED, SCENARIO_NOT_CERTIFIED |

No SD, IQR or CV is reported as between-run repeatability from the 957 telemetry rows or from the 3 diagnostic phase record(s). A single session's within-run variation is **not** a run-to-run variance estimate.

The complete per-phase/per-metric table, including undefined reasons and
denominators, is `repeatability-summary.csv`. Synthetic positive controls
used by the tests are never inserted into this physical report.

## 9. Confounding-variable inventory

| Factor | Status | Evidence | Source field | Quality | Owner | Note |
|---|---|---|---|---|---|---|
| Initial chamber temperature | OBSERVED | 29.916667 °C at the first full-term tmean_airroles_v0 sample | t1,t3,t4 role-qualified through W04 normalized capture | THERMAL_VALID; RUN_NOT_PHYSICALLY_QUALIFIED | A measures / B consumes | measured pre-intervention; the run itself is diagnostic-only under the W04 admission ladder |
| Initial thermal gradient / spatial spread | OBSERVED | initial spread 0.374000 °C (max-min across chamber probes) | t1,t3,t4 per-row spread | THERMAL_VALID; DIAGNOSTIC_ONLY | A measures / B consumes | spread is a spatial proxy, not a heat-flux or product-quality measure |
| Ambient temperature and relative humidity | UNQUALIFIED | BME values are carried but the environment quality domain is UNQUALIFIED | air_c, rh_pct, pressure_hpa | ENVIRONMENT_UNKNOWN | A/C | not treated as controlled; no inference that ambient was constant |
| Hardware and session identity | NOT_CARRIED | boot_id='56044b74'; device_id=None; hardware_config_id='CG-HW-001' | capture run identity | HARDWARE_DECLARED_NOT_VERIFIED | A/C | device identity is not carried by this encoding; the hardware configuration is a declared label, not a verified identity |
| Calibration identity | NOT_CARRIED | calibration_id=None | capture run identity | CALIBRATION_NOT_AVAILABLE | A | no calibration identity exists; it is never invented |
| Firmware and controller version | NOT_CARRIED | firmware_version='cg-w04-0.1.0'; controller_id=None | capture run identity | FIRMWARE_CARRIED; CONTROLLER_NOT_CARRIED | A/C/D | controller identity is absent; firmware identity alone does not bind a treatment arm |
| Sensor placement and role | OBSERVED | operator-frozen 2026-11-02 probe identification: T1 centre, T2 hot side, T3 bottom, T4 near door | sensor role records in the W04 capture | POSITION_OPERATOR_FROZEN; ROM_READBACK_NOT_VERIFIED | A | response-identified mapping, not an independent ROM readback, installed-geometry measurement or calibration |
| Load state and chamber geometry | UNKNOWN | no load or geometry field is carried | not carried | UNKNOWN | A | cannot be held constant or compared across runs from this source |
| Previous run / thermal history | UNKNOWN | no prior-session state or heat-accumulation history is carried | not carried | UNKNOWN | A/C | the single session is the first in this dossier; earlier history is unknown |
| Initial cooling and door state | UNQUALIFIED | applied cooling OFF before the step; door tokens {'CLOSED': 131} | pwm_applied_permille, door_open/door_polarity | COOLING_OFF_OBSERVED; DOOR_UNQUALIFIED | A | door state is UNKNOWN for 17 rows and unqualified throughout |
| Cooling duty profile | OBSERVED | applied duty 999–999 permille; requested differs on 600 rows | pwm_applied_permille, pwm_req_permille | DEVICE_REPORTED_APPLIED_STATE; NOT_COMMAND_PROOF | A | applied duty is observed; it is not a verified electrical envelope |
| Cooling-branch electrical qualification | UNQUALIFIED | electrical rows unqualified: 600 | voltage_v, current_a, power_w, energy_wh | ELECTRICAL_UNKNOWN | A/C | no recorded electrical validity; numeric summaries are diagnostic-only; no energy, COP or whole-system claim |
| Door disturbance history | UNKNOWN | door state is CLOSED/UNKNOWN but door quality is unqualified and no disturbance event is certified | door_open, door_polarity | DOOR_UNQUALIFIED | A | no door-open event in this session; absence of a qualified event is not proof of no disturbance |
| Timing and acquisition cadence | OBSERVED | median dt 1.0 s; p95 1.0 s; long gaps 0 | device_ms, seq | BOOT_SCOPED_UPTIME; CLOCK_SYNC_NOT_EVIDENCED | A/C | boot-relative order only; no cross-boot or absolute-time alignment |
| Recovery / reset-state condition | UNQUALIFIED | recovery end 26.645667 °C vs pre-action 30.021000 °C; reset criterion unresolved | role-qualified chamber-air representation | CENSORED_AT_CAPTURE_END; RESET_CRITERION_UNRESOLVED | A/D | the run ends without a frozen reset criterion; recovery is censored |
| Sensor drift and aging | UNKNOWN | no repeated calibration, drift check or probe cross-check exists | not carried | UNKNOWN | A | a single session cannot separate sensor drift from plant variation; absent calibration is not evidence of a stable calibration |
| Run order and session-day effects | NOT_COMPARABLE | one boot session; no randomized or balanced run order | capture session identity | SINGLE_SESSION | A/B | cannot estimate order, day, ambient-drift or operator-learning effects |

Because no certified independent repeated runs exist, run-to-run confounding cannot be quantified. Unmeasured factors are marked rather than assigned artificial variability.

## 10. Pairing candidate variables

See `ml/pairing-candidate-variables.md` (generated by the same run). It
distinguishes matching variables, outcomes, measured covariates, protocol
constraints and unavailable variables. No numeric tolerance is claimed.

## 11. Limitations and external dependencies

- 1 boot session(s), 2 source run-id label(s) and 3 phase segment(s); no independent experimental repetition exists.
- W04 admission is `EXCLUDED_OR_BLOCKED`; the highest stage is `USABLE_FOR_DIAGNOSTIC_QA`.
- Device identity is not carried; run identity is unresolved; hardware
  configuration is declared, not verified; calibration identity is absent.
- Sensor positions are operator-frozen evidence, not an independent ROM
  readback, installed-geometry measurement or calibration.
- A-W07-01 remains PARTIAL: V1 position, cable paths, door alignment,
  internal load, conductor/termination evidence and the configuration
  photo/drawing are not frozen in the committed evidence.
- Door state and ambient environment are unqualified; electrical values are
  unqualified.
- The canonical docs/01 §20.1 `mean(T1,T2,T3)` naming disagrees with the
  as-built rig; this report uses role-qualified naming and publishes the
  literal expression only as a named non-air cross-check.
- No physical action, no Controller A/B comparison, no model training and no
  W08–W12 implementation is performed or claimed.

## 12. Reproduce

```bash
python scripts/plant-eda-W07.py --source ../evidence/A/W09/exports/CG-S1-H8C-600S.json --a-run-index ../evidence/A/W09/s1-run-index.json --a-w07-dir ../evidence/A/W07 --out reports/W07 --representation tmean_airroles_v0 --trailing-samples 120 --temperature-change-thresholds 1.0,2.0 --min-runs 3 --percentile-method linear --repository-revision 3f1829ab52d431262047707040f61f6f276dea51
```

Repeated execution against the same source and configuration produces
identical analytical content; the manifest records the source SHA-256, the
analysis code SHA-256, the estimator settings and artifact hashes.
