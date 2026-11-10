# W19 Pair-Ledger Contract (B-W19-01)

Evidence class: SYNTHETIC_SOFTWARE_CONTROL_ONLY (software verification; no physical campaign data).

Evidence labels: ACTUAL_REPO_EVIDENCE (committed W15/W16/W17/W18 artifacts and Member B contracts), SYNTHETIC_SOFTWARE_FIXTURE (permanently marked W19 fixture ledger), DERIVED_SOFTWARE_ASSERTION (ledger/validity/progress results), EXTERNAL_DEPENDENCY (A/C/D and leader prerequisites), NOT_VERIFIED (absent physical campaign data).

## Scope

Schema: `coldguard-w19-pair-ledger-v1`; layer: `coldguard-w19-paired-campaign-integrity-v1`; base revision `54c030ce9096a7e85b62570420f6596ff756d4f3` (W18_STACK_HEAD_BASE_NOT_W19_DELIVERY_COMMIT).

The statistical unit is one valid matched Controller A/B pair. A physical run is one arm of a pair; a telemetry row or feature window is never an independent A/B observation. One pair contributes at most one paired observation to the eventual W20 analysis.

## Pair identity fields

| Field | Level | Rule |
|---|---|---|
| pair_id | pair | unique ledger identity |
| campaign_id / scenario_id / block_id / session_id | pair + attempt | must agree |
| planned_controller_order | pair | registered A/B permutation |
| actual_controller_order | pair | recorded permutation, must equal planned |
| run_id / attempt_id | attempt | globally unique |
| controller_arm | attempt | A or B; exactly one selected terminal arm each |
| hardware_config_id / calibration_id / firmware_version | attempt | match across arms and campaign freeze |
| model_artifact_id / model_artifact_sha256 / feature_version | attempt | Controller B identity; frozen model only |
| policy_version / protocol_version / disturbance_protocol_id | attempt | frozen controller/protocol identity |
| source_path / source_manifest_id / source_sha256 | attempt | provenance; SHA-256 bound |
| quality_status / validity_status / validity_reason_codes | attempt | predeclared outcomes only |
| validity_method / audit_events / corrections | attempt | append-only decision history |
| initial_state | pair | comparability evidence and criterion version |

## Pair state machine

| Status | Transition evidence |
|---|---|
| PLANNED | pair exists, no attempt recorded |
| AWAITING_SECOND_ARM | exactly one terminal arm recorded |
| AWAITING_VALIDITY | both arms recorded, validity review pending |
| PAIR_VALID | both arms VALID + matching + registered order + frozen tolerances + initial comparability |
| PAIR_INVALID | a proven protocol/matching/comparability violation, or the frozen rule invalidates the pair |
| PAIR_BLOCKED_MISSING_FREEZE | an invalid-arm rule, matching policy or registered order is not frozen |
| PAIR_UNRESOLVED | ambiguous history, missing evidence, duplicate identity, drift or an incomplete rerun |

A pair never becomes VALID merely because two run IDs exist.

## Attempt history and rerun semantics

Every attempt is retained: initial, aborted, invalid, eligible reruns and superseded attempts. A rerun keeps the original `pair_id` and controller arm, declares `supersedes`, and the superseded record keeps its invalid status. Reusing the same `run_id` or source hash anywhere is refused. Corrections are explicit records; nothing is silently overwritten.

## Synthetic fixture policy

Every fixture attempt carries `TEST_ONLY` and `SYNTHETIC_SOFTWARE_CONTROL_ONLY`. A fixture-marked record can never be physically admitted, and a synthetic ledger cannot claim authorization.

Fixture pairs: 1; fixture attempts: 2. Full pair rows are not reported as campaign data.

## Adversarial controls

| Control | Expectation | Passed |
|---|---|---|
| valid_pair_control | one protocol-valid synthetic pair is PAIR_VALID but never physically admitted | True |
| two_a_arms_refused | two A arms cannot form a pair | True |
| three_arms_refused | three terminal arms are ambiguous | True |
| duplicate_run_id_refused | a run id may appear once | True |
| duplicate_source_refused | one physical source cannot appear twice | True |
| scenario_mismatch_refused | scenario must match | True |
| hardware_mismatch_refused | hardware configuration must match | True |
| calibration_mismatch_refused | calibration lineage must match | True |
| order_deviation_refused | actual order must follow the registered order | True |
| randomization_missing_blocks | an unregistered order cannot produce a valid pair | True |
| unfrozen_tolerances_block | pilot-era tolerances are not an approved matching policy | True |
| initial_tolerance_refused | initial-state delta beyond the frozen tolerance invalidates the pair | True |
| invalid_arm_requires_frozen_rule | a failure cannot trigger an automatic rerun or invalidation | True |
| invalid_arm_rerun_pending | an invalid arm contributes zero valid pairs until a rerun completes | True |
| rerun_preserves_attempt_history | a permitted rerun keeps the invalid attempt and the original pair identity | True |
| fixture_in_physical_refused | a marked fixture can never enter a physical ledger | True |
| outcome_injection_refused | an outcome column cannot enter the ledger validation route | True |
| missing_source_hash_refused | an attempt without a source hash is not physical evidence | True |
| fake_authorization_refused | an authorization claim without authority/evidence is refused | True |
| fixture_never_authorized | a synthetic ledger cannot claim physical authorization | True |
| rerun_of_valid_arm_refused | a protocol-valid arm cannot be replaced by an eligible-looking rerun | True |
| invalidate_policy_not_bypassed_by_rerun | a frozen INVALIDATE_PAIR rule cannot be bypassed by a rerun | True |
| null_freeze_value_not_approved | a frozen field without a value blocks campaign freeze approval | True |

```text
PAIR_LEDGER_SCHEMA = VERIFIED
PAIR_LEDGER_SOFTWARE = VERIFIED
PHYSICAL_PAIR_LEDGER_EVIDENCE = NOT_ESTABLISHED
SYNTHETIC_FIXTURES_ADMITTED = 0
```

No approval, signature, date or signoff record is fabricated by this report.
