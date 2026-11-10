# W20 Pair-Outcomes Contract (B-W20-02) — Schema Only

Evidence class: METADATA_ONLY_FOR_REAL_CAMPAIGN plus TEST_ONLY_SOFTWARE_GATE_PROOF; no physical campaign or outcome data is present.

Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17/W18/W19 artifacts, Member A W19/W20 metadata dossiers and Member B contracts), SYNTHETIC_SOFTWARE_FIXTURE (permanently marked W20 fixture metadata), DERIVED_SOFTWARE_ASSERTION (gate, contract and causal-boundary results), EXTERNAL_DEPENDENCY (Member A/C/D and leader prerequisites), NOT_VERIFIED (absent physical campaign data and outcome payloads).

## Output contract

Schema `coldguard-w20-pair-outcomes-v1`; file `pair-outcomes.csv`; statistical unit: one valid matched Controller A/B pair.

| Column | Type | Role | Required | Canonical ref |
|---|---|---|---|---|
| pair_id | string | IDENTITY | True | 03 §95-98 |
| run_A_id | string | IDENTITY | True | 03 §34-37, §95-98 |
| run_B_id | string | IDENTITY | True | 03 §34-37, §95-98 |
| controller_order | string | IDENTITY | True | 03 §36 |
| hardware_config_id | string | IDENTITY | True | 03 §35 |
| calibration_id | string | IDENTITY | True | 03 §35 |
| firmware_version | string | IDENTITY | True | 03 §92 |
| model_artifact_sha256_B | string | IDENTITY | True | 03 §92 |
| source_sha256_A | string | IDENTITY | True | 03 §158-163 |
| source_sha256_B | string | IDENTITY | True | 03 §158-163 |
| analysis_version | string | IDENTITY | True | 03 §130-135 |
| primary_outcome_name | string | IDENTITY | True | 03 §133 |
| primary_outcome_version | string | IDENTITY | True | 03 §133 |
| A_value | number|UNDEFINED | PRIMARY_VALUE | True | 03 §74 |
| B_value | number|UNDEFINED | PRIMARY_VALUE | True | 03 §74 |
| paired_improvement | number|UNDEFINED | PRIMARY_VALUE | True | 03 §74 |
| thermal_exposure_c_s | number|UNDEFINED | SECONDARY_VALUE | True | 03 §68-69 |
| recovery_time_s | number|CENSORED|UNDEFINED | SECONDARY_VALUE | True | 03 §70 |
| peak_temperature_c | number|UNDEFINED | SECONDARY_VALUE | True | 03 §71 |
| time_above_limit_s | number|UNDEFINED | SECONDARY_VALUE | True | 03 §71 |
| branch_energy_wh | number|UNDEFINED | SECONDARY_VALUE | True | 03 §72 |
| supporting_outcomes_json | object|UNDEFINED | SECONDARY_VALUE | False | 05B §48 |
| coverage_status | object | METADATA_ONLY | True | 03 §130-135 |
| undefined_reason_codes | array | METADATA_ONLY | True | metric-spec §6-8 |
| validity_flags | object | METADATA_ONLY | True | 03 §95-98 |
| metric_versions | object | METADATA_ONLY | True | 03 §130-135 |

## Metric definitions and undefined rules

### thermal_exposure (degC*s)

- Scope: PAIR_ARM_COOLING_ZONE
- Formula contract: `E_T = integral max(0, T(t) - T_limit) dt`
- Canonical ref: 03 §68-69; metric-spec §6
- Required inputs: representative_temperature_series, frozen_t_limit, quality_flags, coverage_spans
- Undefined policy: missing or corrupted spans are excluded and coverage is reported; coverage below the frozen floor makes the outcome undefined; no interpolation across gaps and no zero fill; the representative-temperature choice is frozen before the campaign
- Zero fill forbidden: true
- Whole-system energy forbidden: false

### recovery_time (s)

- Scope: PAIR_ARM_COOLING_ZONE
- Formula contract: `T_recovery = t_recovered - t_reference`
- Canonical ref: 03 §70; metric-spec §7
- Required inputs: representative_temperature_series, frozen_recovery_reference, frozen_recovery_band, frozen_recovery_persistence, coverage_spans
- Undefined policy: an unfinished recovery is CENSORED, never a finite recovery time; a missing crossing is undefined, never zero; electrical observation cannot substitute for thermal recovery
- Zero fill forbidden: true
- Whole-system energy forbidden: false

### peak_temperature (degC)

- Scope: PAIR_ARM_COOLING_ZONE
- Formula contract: `max(T(t)) over the frozen measurement window`
- Canonical ref: 03 §71; metric-spec §6
- Required inputs: representative_temperature_series, frozen_time_base
- Undefined policy: one physical measurement and one time base are used for both arms; post-hoc selection of a more favorable representation is forbidden
- Zero fill forbidden: true
- Whole-system energy forbidden: false

### time_above_limit (s)

- Scope: PAIR_ARM_COOLING_ZONE
- Formula contract: `sum(dt_i where T_i > T_limit)`
- Canonical ref: 03 §71; metric-spec §6
- Required inputs: representative_temperature_series, frozen_t_limit, frozen_time_base
- Undefined policy: one physical measurement and one time base are used for both arms; gaps are excluded with coverage reported; no zero fill
- Zero fill forbidden: true
- Whole-system energy forbidden: false

### branch_energy (Wh)

- Scope: COOLING_BRANCH_PZEM_ONLY
- Formula contract: `E_Wh = sum(P_i * dt_i) / 3600 over the cooling branch`
- Canonical ref: 03 §72, §102; metric-spec §8
- Required inputs: cooling_branch_power_or_validated_counter, coverage_spans, counter_reset_log
- Undefined policy: missing PZEM samples are missing spans, never zero Wh; counter resets are segmented and logged; unresolvable spans are undefined; cooling-branch energy must never be labelled whole-system energy
- Zero fill forbidden: true
- Whole-system energy forbidden: true

## Admission plan (metadata only)

| Pair | Run A | Run B | Status | Problems |
|---|---|---|---|---|

Admission verdict: BLOCKED_NO_VALID_PAIR

## Withheld artifacts

```text
OUTCOME_TABLE = PAIR_OUTCOME_TABLE_NOT_PRODUCED
PHYSICAL_OUTCOME_DATA = PHYSICAL_OUTCOME_DATA_NOT_ADMITTED
OUTCOME_SCHEMA = OUTCOME_SCHEMA_SOFTWARE_VERIFIED
PAIR_LEDGER_FINAL = WITHHELD_NO_ACCEPTED_PHYSICAL_CAMPAIGN
PAIR_OUTCOMES_CSV = WITHHELD_UNTIL_SEPARATE_AUTHORIZED_EXECUTION
```

No outcome value is computed, admitted or written. Missing coverage is reported as undefined/censored and is never converted to zero.

Current gate decision: ANALYSIS_PREFLIGHT_BLOCKED.
