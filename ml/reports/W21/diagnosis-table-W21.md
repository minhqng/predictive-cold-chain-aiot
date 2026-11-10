# W21 Diagnosis Table (B-W21-01)

Evidence class: `ON_DEVICE_SOFTWARE_INJECTION` for the two recorded cases; `SOFTWARE_TEST_ONLY` for the contract controls. The actuator output stage was compiled out, the fuse was OUT and the TEC was OFF throughout.

Scope: non-primary diagnosis evidence only. No model retraining, no threshold/horizon/persistence change and no physical acceptance.

## Source-bound recorded cases

| Case | Condition | Ground truth | Measurement evidence | Quality | Expected | Observed | Concordance | Independent sessions | Source SHA-256 |
|---|---|---|---|---|---|---|---|---:|---|
| A-W21-02 | single DS18B20 chamber-air role T1 software injection on the real ESP32-S3 | CONTROLLED_INJECTION (evidence/A/W21/fault-injection-session-20261108/events.json::B_ds_t1_on) | 25 frames; T1 explicitly invalid; overall UNKNOWN; thermal DEGRADED; ROM map unchanged; 25/25 valid recovery frames | overall=UNKNOWN; thermal=DEGRADED; electrical=UNKNOWN; current=UNKNOWN | DEGRADED_OR_UNKNOWN | DEGRADED_OR_UNKNOWN | CONCORDANT_BOUNDED | 1 | `4fbc22d3150d3e67a8e1c2556543c454e68e835426d8fd66a3bc0f6949b1682b` |
| A-W21-03 | PZEM transport-boundary software disable | CONTROLLED_INJECTION (evidence/A/W21/fault-injection-session-20261108/events.json::C_pzem_on) | 25 frames; electrical INVALID 24 / VALID 1; overall INVALID 24 / UNKNOWN 1; current missing; never carried forward; 24/25 valid recovery frames | overall=INVALID; thermal=UNKNOWN; electrical=INVALID; current=MISSING | DEGRADED_OR_UNKNOWN | DEGRADED_OR_UNKNOWN | CONCORDANT_BOUNDED | 1 | `b8bb30ba309bd90a555bb99d8c30dca289a15fd1559628937bf069142e8c8cdc` |

Expected classifications are derived from the recorded injection condition and the canonical DIAG mapping; they are not an independent external evaluator label. Concordance is bounded to these two controlled cases and is not a population accuracy estimate.

## Canonical DIAG-01..04 comparison

| Case | Condition | Expected | Status | Reason |
|---|---|---|---|---|
| DIAG-01 | healthy | HEALTHY_RESPONSE | NOT_ESTIMABLE | NO_ENABLED_ACTUATOR_OBSERVATION |
| DIAG-02 | electrical response missing | ELECTRICAL_RESPONSE_MISSING | NOT_ESTIMABLE | NO_ENABLED_ACTUATOR_OBSERVATION; A-W21-03 IS A PZEM TRANSPORT DISABLE, NOT A COMMANDED TEC FAILING TO DRAW CURRENT |
| DIAG-03 | unexpected current while OFF | UNEXPECTED_OFF_CURRENT | NOT_ESTIMABLE | NO_OBSERVED_OFF_WITH_CURRENT |
| DIAG-04 | degraded thermal effectiveness | DEGRADED_THERMAL_EFFECTIVENESS | NOT_ESTIMABLE | NO_SAFE_PHYSICAL_DEGRADATION_OBSERVATION |

The recorded session contains no healthy enabled-actuator observation. The DIAG-01/02 actuator-response comparison is therefore left unestimated; A-W21-03 is a PZEM transport disable under an output-disabled configuration, not a commanded TEC failing to draw current.

## Evidence levels

| Case | Levels supported |
|---|---|
| A-W21-02 | RECORDED_CONDITION_OR_CONTROLLED_INJECTION, TRUSTED_CHANNEL_OBSERVATION, SOFTWARE_DIAGNOSTIC_CLASSIFICATION |
| A-W21-03 | RECORDED_CONDITION_OR_CONTROLLED_INJECTION, TRUSTED_CHANNEL_OBSERVATION, SOFTWARE_DIAGNOSTIC_CLASSIFICATION |

`ROOT_CAUSE_IDENTIFICATION` is never supported by a single observation.

## Refusal and control catalogue

Classifier-emitted refusals are listed first; rows marked `(control)` are driver-level probes, not classifier outputs.

| Refusal | Applied to |
|---|---|
| `MISSING_PZEM_IS_NOT_VERIFIED_ZERO_CURRENT` | A-W21-03 |
| `OUTPUT_STAGE_DISABLED_NO_ACTUATOR_RESPONSE` | A-W21-02, A-W21-03 |
| `SINGLE_OBSERVATION_CANNOT_IDENTIFY_ROOT_CAUSE` | A-W21-02, A-W21-03 |
| `COMMAND_ON_IS_NOT_MEASURED_CURRENT` | on_command_not_current (control) |
| `ACK_IS_NOT_ACTUATION_EVIDENCE` | ack_not_applied_power (control) |
| `ELECTRICAL_CURRENT_IS_NOT_THERMAL_COOLING` | current_not_thermal (control) |
| `EVIDENCE_CLASS_MISMATCH` | software_injection_not_cable_disconnect (control) |
| `WEAK_THERMAL_RESPONSE_IS_NOT_COMPONENT_ROOT_CAUSE` | weak_cooling_not_component (control) |
| `SHARED_BOOT_NOT_INDEPENDENT` | shared_boot_not_independent (control) |

## Unsupported conclusions

- ENABLED_ACTUATOR_ELECTRICAL_RESPONSE
- ENABLED_ACTUATOR_FAIL_SAFE
- FAULT_DETECTION_ACCURACY
- MODEL_ROBUSTNESS_UNDER_SENSOR_LOSS
- PHYSICAL_DS18B20_FAILURE
- PHYSICAL_PZEM_DISCONNECTION
- VERIFIED_ZERO_CURRENT
- WHOLE_SYSTEM_POWER

## Population metrics

| Metric | Value | Reason |
|---|---|---|
| diagnostic_accuracy | NOT_ESTIMABLE | `INSUFFICIENT_INDEPENDENT_LABELED_SUPPORT` |
| fault_recall | NOT_ESTIMABLE | `INSUFFICIENT_INDEPENDENT_LABELED_SUPPORT` |
| precision | NOT_ESTIMABLE | `INSUFFICIENT_INDEPENDENT_LABELED_SUPPORT` |
| false_positive_rate | NOT_ESTIMABLE | `INSUFFICIENT_INDEPENDENT_LABELED_SUPPORT` |

## Independence

- Recorded injection-window frames: 50 (25 + 25).
- Recorded recovery frames: 50 (25 + 25).
- Total recorded frames: 100.
- Independent on-device session count: 1.
- A-W21-02 and A-W21-03 share boot `4cf9be5f`, one raw log and one combined session; they are not two independent physical experiments.
- The acceptance evaluator lineage is not on main; independent evaluator replay remains pending.
