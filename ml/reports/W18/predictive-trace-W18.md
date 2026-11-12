# W18 predictive-intervention trace audit

Evidence class: SYNTHETIC_SOFTWARE_CONTROL_ONLY / TEST_ONLY fixture.
Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17 and Member A files), SYNTHETIC_SOFTWARE_FIXTURE (W17 replay and TEST_ONLY fixture), DERIVED_SOFTWARE_ASSERTION (monitor/trace/freeze/readiness results), EXTERNAL_DEPENDENCY (A/C/D interface snapshots), NOT_VERIFIED (absent live/physical evidence).

## W17 replay stage coverage (actual repo evidence)

| stage | status |
|---|---|
| ack | ABSENT |
| applied_state | ABSENT |
| command | ABSENT |
| physical_verification | ABSENT |
| policy | HYPOTHETICAL_ONLY_NOT_EVALUATED |
| prediction | PRESENT |
| warning | PRESENT_SYNTHETIC_ILLUSTRATIVE |

W17 records summarized: 783; detailed records copied: false.
Trace internal SHA-256: fc9dd80efa418aea651c80342dd0fc3d9b9d353af3b7e794ceee6c61e97a03e4.
Freshness verdicts: {"FRESH": 783}.
Warning statuses: {"NOT_TRIGGERED_SYNTHETIC_ILLUSTRATIVE": 623, "TRIGGERED_SYNTHETIC_ILLUSTRATIVE": 160}.
Policy statuses: {"NOT_EVALUATED": 783}.

W17 trace outcome: TRACE_PARTIAL_MISSING_EVIDENCE.
Physical chain status: PHYSICAL_CHAIN_UNAVAILABLE_NO_AUTHORIZED_POLICY_COMMAND_STAGE.
The W17 replay contains no authorized policy decision, command, ACK or
physical response; the physical chain is unavailable and is not invented.

## TEST_ONLY fixture assessment

Fixture outcome: TRACE_COMPLETE_SOFTWARE_FIXTURE.
fixture=true, physical_verified=false, authorized_control=false, real_intervention=false, controller_b_acceptance=false.

| invariant | status | observed | reason |
|---|---|---|---|
| TR-02 | PASS | prediction_id=pred-w18-test-0001, model=25a8ef7a71817d4d, schema=1d36d338f35dd448 | - |
| TR-01 | PASS | all present stages agree | - |
| TR-08 | PASS | physical attribution matches the trace identity | - |
| TR-07 | PASS | terminal states are consistent | - |
| TR-05 | PASS | chronology is coherent | - |
| TR-11 | PASS | policy status HYPOTHETICAL | - |
| TR-06 | PASS | structurally complete synthetic fixture evidence | - |
| TR-10 | PASS | missing stages: none | - |
| TR-12 | PASS | fixture=True, evidence_class=TEST_ONLY_SYNTHETIC_FIXTURE, physical_evidence_class=SYNTHETIC_TEST_FIXTURE_NOT_PHYSICAL_EVIDENCE, claimed_physical_success=False | - |

## Negative controls

| probe | expected | observed | passed |
|---|---|---|---|
| missing_downstream_stages | TRACE_PARTIAL_MISSING_EVIDENCE | TRACE_PARTIAL_MISSING_EVIDENCE | True |
| missing_applied_state | TRACE_PARTIAL_MISSING_EVIDENCE | TRACE_PARTIAL_MISSING_EVIDENCE | True |
| command_prediction_mismatch | TRACE_INCONSISTENT_IDENTITY | TRACE_INCONSISTENT_IDENTITY | True |
| policy_run_mismatch | TRACE_INCONSISTENT_IDENTITY | TRACE_INCONSISTENT_IDENTITY | True |
| ack_before_command | TRACE_TEMPORAL_CONTRADICTION | TRACE_TEMPORAL_CONTRADICTION | True |
| success_without_physical_verification | TRACE_PHYSICAL_UNVERIFIED | TRACE_PHYSICAL_UNVERIFIED | True |
| fixture_claims_physical_success | TRACE_INCONSISTENT_IDENTITY | TRACE_INCONSISTENT_IDENTITY | True |
| hypothetical_command_unmarked | TRACE_NOT_AUTHORIZED | TRACE_NOT_AUTHORIZED | True |
| thermal_verification_missing | TRACE_PHYSICAL_UNVERIFIED | TRACE_PHYSICAL_UNVERIFIED | True |
| parent_class_only_physical | TRACE_PHYSICAL_UNVERIFIED | TRACE_PHYSICAL_UNVERIFIED | True |
| electrical_quality_unknown | TRACE_PHYSICAL_UNVERIFIED | TRACE_PHYSICAL_UNVERIFIED | True |
| claimed_success_without_command | TRACE_PHYSICAL_UNVERIFIED | TRACE_PHYSICAL_UNVERIFIED | True |
| applied_state_without_physical | TRACE_PHYSICAL_UNVERIFIED | TRACE_PHYSICAL_UNVERIFIED | True |
| physical_without_command | TRACE_NOT_AUTHORIZED | TRACE_NOT_AUTHORIZED | True |
| synthetic_fixture_mislabeled | TRACE_INCONSISTENT_IDENTITY | TRACE_INCONSISTENT_IDENTITY | True |
| authorized_without_evidence | TRACE_NOT_AUTHORIZED | TRACE_NOT_AUTHORIZED | True |
| terminal_status_contradiction | TRACE_INCONSISTENT_IDENTITY | TRACE_INCONSISTENT_IDENTITY | True |
| physical_attribution_cross_boot | TRACE_INCONSISTENT_IDENTITY | TRACE_INCONSISTENT_IDENTITY | True |

## Physical boundary

- An ACK is an acknowledgement only; it is never electrical or thermal evidence.
- Applied state is a device report; it is not independent physical verification.
- The synthetic fixture proves parsing and refusal behavior, not physical execution.
- No record in this audit establishes a real predictive intervention.
- A measured physical trace evidence class is not accepted in this W18
  software scope; adding one is scheduled before any authorized physical run.
