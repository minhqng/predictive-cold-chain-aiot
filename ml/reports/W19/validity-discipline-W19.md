# W19 Outcome-Blinded Validity Discipline (B-W19-02)

Evidence class: SYNTHETIC_SOFTWARE_CONTROL_ONLY (software verification; no physical campaign data).

Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17/W18 artifacts and Member B contracts), SYNTHETIC_SOFTWARE_FIXTURE (permanently marked W19 fixture ledger), DERIVED_SOFTWARE_ASSERTION (ledger/validity/progress results), EXTERNAL_DEPENDENCY (A/C/D and leader prerequisites), NOT_VERIFIED (absent physical campaign data).

## Separation of validity and outcome

Validity review asks whether a run met the frozen protocol. Outcome analysis asks whether Controller B improved the physical result. W19 implements only the former; final outcome analysis remains locked to W20.

The validity input contract carries identity, hardware/calibration provenance, protocol version, disturbance execution, reset eligibility, quality/completeness flags, time/sequence validity, the controller-order record and predeclared reason codes. It has no exposure, recovery, energy, p-value or effect-size field, so treatment direction cannot enter the decision.

## Predeclared reason codes

| Reason code |
|---|
| ATTEMPT_ABORTED |
| CALIBRATION_PROVENANCE_MISSING |
| CONTROLLER_ORDER_RECORD_MISSING |
| DISTURBANCE_NOT_EXECUTED |
| DISTURBANCE_STATUS_UNKNOWN |
| DISTURBANCE_TOLERANCE_EXCEEDED |
| FIRMWARE_IDENTITY_MISSING |
| HARDWARE_IDENTITY_MISSING |
| INITIAL_RESET_CRITERION_NOT_MET |
| INITIAL_RESET_EVIDENCE_MISSING |
| PHYSICAL_QUALITY_INVALID |
| PHYSICAL_QUALITY_UNVERIFIED |
| PRIMARY_OUTCOME_COMPLETENESS_UNKNOWN |
| PROTOCOL_VERSION_MISSING |
| SAFETY_STOP_RECORDED |
| TELEMETRY_GAP_COVERS_PRIMARY_EVENT |
| TEMPORAL_ORDER_INVALID |
| TEMPORAL_ORDER_UNVERIFIED |
| UNPROTOCOL_OPERATOR_INTERVENTION |

## Metric-specific completeness

| Metric | Role | Coverage key | Rule |
|---|---|---|---|
| thermal_exposure | PRIMARY | thermal_primary | missing/incomplete primary coverage invalidates the attempt; a missing secondary metric is UNDEFINED_INCOMPLETE, never zero-filled |
| recovery_time | SECONDARY | thermal_recovery | missing/incomplete primary coverage invalidates the attempt; a missing secondary metric is UNDEFINED_INCOMPLETE, never zero-filled |
| branch_energy | SECONDARY | electrical_energy | missing/incomplete primary coverage invalidates the attempt; a missing secondary metric is UNDEFINED_INCOMPLETE, never zero-filled |

## Invariants

- A pair where Controller B performs worse can still be perfectly valid.
- A pair where Controller B performs better is rejected when protocol-invalid.
- Swapping A/B performance cannot change eligibility because performance is not an input.
- An invalid primary arm cannot count as a valid pair.
- A decision without objective recorded reasons is structurally refused.
- Missing PZEM coverage is reported as undefined, never as zero energy.

## Controls

| Control | Expectation | Passed |
|---|---|---|
| protocol_valid_worse_b_retained | a protocol-valid B arm stays valid regardless of performance | True |
| protocol_invalid_better_b_rejected | a protocol-invalid B arm is rejected regardless of performance | True |
| arm_swap_does_not_change_validity | controller-arm identity is not an outcome and cannot change validity | True |
| validity_outcome_payload_refused | the validity route refuses outcome-shaped fields | True |
| missing_energy_stays_undefined | missing PZEM coverage is undefined, never zero energy | True |
| primary_gap_invalidates | a primary-outcome telemetry gap invalidates the attempt | True |
| invalid_decision_records_reasons | no refusal without objective, recorded reasons | True |
| validity_input_carries_no_outcomes | the validity API has no outcome parameter or field | True |

```text
VALIDITY_REVIEW = SOFTWARE_VERIFIED
OUTCOME_FIELDS_IN_VALIDITY_PATH = 0
FINAL_OUTCOME_ANALYSIS = LOCKED
```

No approval, signature, date or signoff record is fabricated by this report.
