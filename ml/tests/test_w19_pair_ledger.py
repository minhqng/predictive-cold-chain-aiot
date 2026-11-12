"""W19 B-W19-01 pair-ledger adversarial controls.

The ledger must preserve every attempt, refuse synthetic fixtures in a physical
campaign, and never promote a pair to VALID without a complete matching, order,
initial-state and freeze record.
"""

from __future__ import annotations

import copy
import hashlib

import pytest

from coldguard_ml.w19_no_peeking import FREEZE_FROZEN_APPROVED
from coldguard_ml.w19_pair_ledger import (
    AUTHORIZATION_AUTHORIZED,
    AUTHORIZATION_FAKE_APPROVAL,
    AUTHORIZATION_NOT_AUTHORIZED,
    CAMPAIGN_FREEZE_FIELD_IDS,
    DEVELOPMENT_BASELINE_DOES_NOT_IMPLY_FREEZE,
    EVIDENCE_PHYSICAL_CAMPAIGN,
    FAILURE_INVALIDATE_PAIR,
    FREEZE_STATUS_APPROVED,
    FREEZE_STATUS_INCOMPLETE,
    FREEZE_STATUS_MISSING,
    PAIR_AWAITING_SECOND_ARM,
    PAIR_AWAITING_VALIDITY,
    PAIR_BLOCKED_MISSING_FREEZE,
    PAIR_INVALID,
    PAIR_PLANNED,
    PAIR_UNRESOLVED,
    PAIR_VALID,
    W19LedgerError,
    assess_campaign_freeze,
    build_test_only_fixture_ledger,
    compare_campaign_freeze,
    evaluate_campaign_authorization,
    validate_pair_ledger,
)

MODEL_SHA = hashlib.sha256(b"W19-FIXTURE-MODEL-ARTIFACT").hexdigest()


def _fixture() -> dict:
    return build_test_only_fixture_ledger()


def _mutated(mutator) -> object:
    document = _fixture()
    mutator(document)
    return validate_pair_ledger(document)


def _attempt(document: dict, arm: str, attempt_id: str | None = None) -> dict:
    for attempt in document["attempts"]:
        if attempt["controller_arm"] != arm:
            continue
        if attempt_id is None or attempt["attempt_id"] == attempt_id:
            return attempt
    raise AssertionError(f"no attempt for arm {arm!r}")


def _add_attempt(
    document: dict,
    *,
    attempt_id: str,
    run_id: str,
    arm: str = "B",
    kind: str = "INITIAL",
    supersedes: str | None = None,
    validity: str = "VALID",
    quality: str = "QUALITY_PASS",
    reasons: tuple[str, ...] = (),
) -> dict:
    base_arm = "B" if arm == "B" else "A"
    new = copy.deepcopy(_attempt(document, base_arm))
    new["attempt_id"] = attempt_id
    new["run_id"] = run_id
    new["controller_arm"] = arm
    new["attempt_kind"] = kind
    new["supersedes"] = supersedes
    new["superseded_by"] = None
    new["quality_status"] = quality
    new["validity_status"] = validity
    new["validity_reason_codes"] = list(reasons)
    new["source_sha256"] = hashlib.sha256(attempt_id.encode("utf-8")).hexdigest()
    new["source_path"] = f"test://w19/fixture/{attempt_id}"
    new["audit_events"] = [
        {"seq": 1, "event": "ATTEMPT_CREATED", "actor": "test-fixture"}
    ]
    document["attempts"].append(new)
    document["pairs"][0]["attempt_ids"].append(attempt_id)
    if supersedes is not None:
        old = next(
            (
                attempt
                for attempt in document["attempts"]
                if attempt["attempt_id"] == supersedes
            ),
            None,
        )
        if old is not None:
            old["superseded_by"] = attempt_id
            old["audit_events"] = old["audit_events"] + [
                {"seq": 3, "event": "ATTEMPT_SUPERSEDED", "actor": "test-fixture"}
            ]
    return new


def _append_second_pair(
    document: dict,
    *,
    run_id_a: str = "RUN-TEST-002-A",
    run_id_b: str = "RUN-TEST-002-B",
    duplicate_source_of_a: bool = False,
) -> None:
    pair = copy.deepcopy(document["pairs"][0])
    pair["pair_id"] = "PAIR-TEST-002"
    pair["attempt_ids"] = []
    for arm in ("A", "B"):
        source = _attempt(document, arm)
        attempt = copy.deepcopy(source)
        attempt["pair_id"] = "PAIR-TEST-002"
        attempt["attempt_id"] = f"ATT-TEST-002-{arm}"
        attempt["run_id"] = run_id_a if arm == "A" else run_id_b
        if duplicate_source_of_a and arm == "A":
            attempt["source_sha256"] = source["source_sha256"]
        else:
            attempt["source_sha256"] = hashlib.sha256(
                f"W19-FIXTURE-PAIR-002-{arm}".encode("utf-8")
            ).hexdigest()
        attempt["source_path"] = f"test://w19/fixture/pair-002/run-{arm}"
        pair["attempt_ids"].append(attempt["attempt_id"])
        document["attempts"].append(attempt)
    document["pairs"].append(pair)
    document["randomization"]["order_list"].append(
        {"pair_id": "PAIR-TEST-002", "planned_order": ["A", "B"]}
    )


def _campaign_freeze_record() -> dict:
    values = {
        "hardware_config_id": "CG-HW-FIXTURE-001",
        "calibration_id": "CG-CAL-FIXTURE-001",
        "firmware_version": "fw-fixture-1.0.0",
        "model_artifact_sha256": MODEL_SHA,
        "controller_policy_version": "test-fixture-predictive-policy-v1",
        "disturbance_protocol": "DOOR-DISTURBANCE-FIXTURE-v1",
        "initial_reset_criterion": "CG-RESET-FIXTURE-v1",
    }
    return {
        "fields": {
            field_id: {
                "value": values.get(field_id, f"FROZEN-{field_id}"),
                "provenance": "test://w19/fixture-freeze",
                "status": FREEZE_FROZEN_APPROVED,
            }
            for field_id in CAMPAIGN_FREEZE_FIELD_IDS
        },
        "approval": {
            "authority_id": "TEST_FIXTURE_ONLY",
            "authority_role": "TEAM_LEAD",
            "canonical_ref": "test://w19/fixture-freeze-approval",
        },
    }


def _admitted_fixture() -> dict:
    document = _fixture()
    document["evidence_class"] = EVIDENCE_PHYSICAL_CAMPAIGN
    for attempt in document["attempts"]:
        attempt["fixture_markers"] = []
    document["campaign_authorization"] = {
        "authorized": True,
        "authority_id": "TEST_FIXTURE_ONLY",
        "authority_role": "TEAM_LEAD",
        "canonical_ref": "test://w19/fixture-authorization",
        "g4_status": "READY",
        "pair_target_frozen": True,
        "analysis_freeze_accepted": True,
    }
    document["campaign_freeze"] = _campaign_freeze_record()
    return document


def _invalid_arm(document: dict, arm: str = "B") -> None:
    attempt = _attempt(document, arm)
    attempt["quality_status"] = "QUALITY_FAIL"
    attempt["validity_status"] = "INVALID"
    attempt["validity_reason_codes"] = ["PHYSICAL_QUALITY_INVALID"]


def test_exactly_one_valid_a_and_b_arm_is_pair_valid():
    result = validate_pair_ledger(_fixture())
    assert result.pairs[0].status == PAIR_VALID
    assert result.pairs[0].selected_attempts == {
        "A": "ATT-TEST-001-A",
        "B": "ATT-TEST-001-B",
    }
    assert result.software_valid_pairs == 1


def test_two_a_arms_are_not_a_pair():
    def mutate(document: dict) -> None:
        _attempt(document, "B")["controller_arm"] = "A"

    result = _mutated(mutate)
    assert result.pairs[0].status != PAIR_VALID
    assert result.pairs[0].status == PAIR_UNRESOLVED
    assert "AMBIGUOUS_ARM_HISTORY" in result.pairs[0].reason_codes


def test_three_arms_assigned_to_one_pair_unresolved():
    def mutate(document: dict) -> None:
        _add_attempt(
            document, attempt_id="ATT-TEST-001-B2", run_id="RUN-TEST-001-B2"
        )

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_UNRESOLVED
    assert "AMBIGUOUS_ARM_HISTORY" in result.pairs[0].reason_codes


def test_same_run_id_in_multiple_attempts_detected():
    def mutate(document: dict) -> None:
        _add_attempt(
            document,
            attempt_id="ATT-TEST-001-A2",
            run_id="RUN-TEST-001-A",
            arm="A",
        )

    result = _mutated(mutate)
    assert "DUPLICATE_RUN_ID_ACROSS_RECORDS" in result.refusal_reasons
    assert not result.ledger_integrity_ok
    assert result.pairs[0].status != PAIR_VALID


def test_same_run_id_across_pairs_detected():
    def mutate(document: dict) -> None:
        _append_second_pair(document, run_id_a="RUN-TEST-001-A")

    result = _mutated(mutate)
    assert "DUPLICATE_RUN_ID_ACROSS_RECORDS" in result.refusal_reasons
    assert all(pair.status != PAIR_VALID for pair in result.pairs)


def test_same_physical_source_under_multiple_run_ids_detected():
    def mutate(document: dict) -> None:
        _append_second_pair(document, duplicate_source_of_a=True)

    result = _mutated(mutate)
    assert "DUPLICATE_SOURCE_SHA256_ACROSS_RECORDS" in result.refusal_reasons
    assert all(pair.status != PAIR_VALID for pair in result.pairs)


def test_pair_id_mismatch_is_a_structural_error():
    def mutate(document: dict) -> None:
        _attempt(document, "B")["pair_id"] = "PAIR-OTHER"

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_scenario_mismatch_invalidates_pair():
    def mutate(document: dict) -> None:
        _attempt(document, "B")["scenario_id"] = "S9_OTHER_SCENARIO"

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "SCENARIO_MISMATCH" in result.pairs[0].reason_codes


def test_hardware_configuration_mismatch_invalidates_pair():
    def mutate(document: dict) -> None:
        _attempt(document, "B")["hardware_config_id"] = "CG-HW-OTHER"

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "HARDWARE_CONFIG_MISMATCH" in result.pairs[0].reason_codes


def test_calibration_and_firmware_incompatibility_invalidates_pair():
    def mutate(document: dict) -> None:
        _attempt(document, "B")["calibration_id"] = "CG-CAL-OTHER"
        _attempt(document, "B")["firmware_version"] = "fw-other"

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "CALIBRATION_LINEAGE_MISMATCH" in result.pairs[0].reason_codes
    assert "FIRMWARE_VERSION_MISMATCH" in result.pairs[0].reason_codes


def test_missing_actual_controller_order_invalidates_pair():
    def mutate(document: dict) -> None:
        document["pairs"][0]["actual_controller_order"] = None

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "CONTROLLER_ORDER_IDENTITY_INVALID" in result.pairs[0].reason_codes


def test_actual_order_must_be_a_valid_permutation():
    def mutate(document: dict) -> None:
        document["pairs"][0]["actual_controller_order"] = ["A", "A"]

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_order_must_follow_the_registered_randomization():
    def mutate(document: dict) -> None:
        document["pairs"][0]["actual_controller_order"] = ["B", "A"]

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "CONTROLLER_ORDER_DEVIATION" in result.pairs[0].reason_codes


def test_registered_order_must_match_planned_order():
    def mutate(document: dict) -> None:
        document["randomization"]["order_list"][0]["planned_order"] = ["B", "A"]

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "CONTROLLER_ORDER_RANDOMIZATION_VIOLATION" in result.pairs[0].reason_codes


def test_unregistered_randomization_blocks_validation():
    def mutate(document: dict) -> None:
        document["randomization"] = {
            "status": "NOT_REGISTERED",
            "seed": None,
            "order_list": None,
            "canonical_ref": None,
        }

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_BLOCKED_MISSING_FREEZE
    assert "RANDOMIZATION_NOT_REGISTERED" in result.pairs[0].reason_codes


def test_aborted_attempt_omitted_from_history_is_detected():
    def mutate(document: dict) -> None:
        document["pairs"][0]["attempt_ids"].append("ATT-MISSING")

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_aborted_attempt_is_preserved_and_awaits_a_valid_rerun():
    def mutate(document: dict) -> None:
        attempt = _attempt(document, "B")
        attempt["attempt_status"] = "ABORTED"
        attempt["validity_status"] = "NOT_APPLICABLE"
        attempt["validity_reason_codes"] = ["ATTEMPT_ABORTED"]

    result = _mutated(mutate)
    assert result.attempt_accounting.aborted_attempts == 1
    assert result.pairs[0].status == PAIR_UNRESOLVED
    assert "PERMISSIBLE_RERUN_NOT_COMPLETED" in result.pairs[0].reason_codes


def test_invalid_attempt_deleted_after_rerun_is_detected():
    def mutate(document: dict) -> None:
        _add_attempt(
            document,
            attempt_id="ATT-TEST-001-B-R1",
            run_id="RUN-TEST-001-B-R1",
            kind="RERUN",
            supersedes="ATT-DELETED",
        )

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_rerun_in_a_different_pair_is_detected():
    def mutate(document: dict) -> None:
        _append_second_pair(document)
        attempt = next(
            item
            for item in document["attempts"]
            if item["attempt_id"] == "ATT-TEST-002-A"
        )
        attempt["attempt_kind"] = "RERUN"
        attempt["supersedes"] = "ATT-TEST-001-A"

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_failed_arm_is_not_silently_paired_with_an_unrelated_later_run():
    def mutate(document: dict) -> None:
        _invalid_arm(document, "A")
        _add_attempt(
            document,
            attempt_id="ATT-TEST-001-A-LATER",
            run_id="RUN-TEST-001-A-LATER",
            arm="A",
        )

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_UNRESOLVED
    assert "AMBIGUOUS_ARM_HISTORY" in result.pairs[0].reason_codes


def test_duplicate_attempt_id_with_conflicting_content_detected():
    def mutate(document: dict) -> None:
        clone = copy.deepcopy(_attempt(document, "B"))
        clone["run_id"] = "RUN-CONFLICTING"
        document["attempts"].append(clone)

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_superseded_attempt_cannot_be_silently_overwritten():
    def mutate(document: dict) -> None:
        _attempt(document, "B")["superseded_by"] = "ATT-GHOST"

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_rerun_preserves_invalid_attempt_and_original_pair_identity():
    def mutate(document: dict) -> None:
        _invalid_arm(document, "B")
        _add_attempt(
            document,
            attempt_id="ATT-TEST-001-B-R1",
            run_id="RUN-TEST-001-B-R1",
            kind="RERUN",
            supersedes="ATT-TEST-001-B",
        )

    document = _fixture()
    mutate(document)
    result = validate_pair_ledger(document)
    assert result.pairs[0].status == PAIR_VALID
    assert result.attempt_accounting.invalid_attempts == 1
    assert result.attempt_accounting.superseded_attempts == 1
    original = _attempt(document, "B", "ATT-TEST-001-B")
    assert original["pair_id"] == "PAIR-TEST-001"
    assert original["validity_status"] == "INVALID"


def test_rerun_of_a_protocol_valid_arm_is_refused():
    def mutate(document: dict) -> None:
        _add_attempt(
            document,
            attempt_id="ATT-TEST-001-B-R1",
            run_id="RUN-TEST-001-B-R1",
            kind="RERUN",
            supersedes="ATT-TEST-001-B",
        )

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "RERUN_OF_NON_INVALID_ARM_REFUSED" in result.pairs[0].reason_codes
    assert result.software_valid_pairs == 0


def test_invalidate_pair_policy_cannot_be_bypassed_by_a_rerun():
    def mutate(document: dict) -> None:
        document["failure_policy"]["invalid_arm_handling"] = FAILURE_INVALIDATE_PAIR
        _invalid_arm(document, "B")
        _add_attempt(
            document,
            attempt_id="ATT-TEST-001-B-R1",
            run_id="RUN-TEST-001-B-R1",
            kind="RERUN",
            supersedes="ATT-TEST-001-B",
        )

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "FROZEN_POLICY_INVALIDATES_PAIR" in result.pairs[0].reason_codes
    assert result.software_valid_pairs == 0


def test_missing_source_hash_is_refused_as_physical_evidence():
    def mutate(document: dict) -> None:
        del _attempt(document, "A")["source_sha256"]

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_synthetic_fixture_misclassified_as_real_is_refused():
    def mutate(document: dict) -> None:
        document["evidence_class"] = EVIDENCE_PHYSICAL_CAMPAIGN

    result = _mutated(mutate)
    assert "FIXTURE_MARKER_IN_PHYSICAL_LEDGER" in result.refusal_reasons
    assert result.pairs[0].status == PAIR_UNRESOLVED
    assert not result.physical_pair_evidence_accepted


def test_synthetic_attempt_must_carry_both_permanent_markers():
    def mutate(document: dict) -> None:
        _attempt(document, "A")["fixture_markers"] = ["TEST_ONLY"]

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_validity_pending_waits_instead_of_passing():
    def mutate(document: dict) -> None:
        attempt = _attempt(document, "B")
        attempt["validity_status"] = "PENDING"
        attempt["validity_reason_codes"] = ["PHYSICAL_QUALITY_UNVERIFIED"]

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_AWAITING_VALIDITY
    assert "ARM_VALIDITY_PENDING" in result.pairs[0].reason_codes


def test_invalid_arm_cannot_count_as_a_valid_pair():
    def mutate(document: dict) -> None:
        _invalid_arm(document, "B")
        document["failure_policy"]["invalid_arm_handling"] = FAILURE_INVALIDATE_PAIR

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "FROZEN_POLICY_INVALIDATES_PAIR" in result.pairs[0].reason_codes
    assert result.software_valid_pairs == 0


def test_frozen_rerun_policy_requires_a_completed_rerun():
    def mutate(document: dict) -> None:
        _invalid_arm(document, "B")

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_UNRESOLVED
    assert "PERMISSIBLE_RERUN_NOT_COMPLETED" in result.pairs[0].reason_codes
    assert result.software_valid_pairs == 0


def test_invalid_arm_without_a_frozen_rule_is_blocked():
    def mutate(document: dict) -> None:
        _invalid_arm(document, "B")
        document["failure_policy"]["status"] = "NOT_FROZEN"

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_BLOCKED_MISSING_FREEZE
    assert "INVALID_ARM_HANDLING_UNFROZEN" in result.pairs[0].reason_codes


def test_unfrozen_matching_tolerances_block_pair_validity():
    def mutate(document: dict) -> None:
        document["matching_policy"]["status"] = "NOT_FROZEN"

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_BLOCKED_MISSING_FREEZE
    assert "PAIR_MATCHING_TOLERANCES_UNFROZEN" in result.pairs[0].reason_codes


def test_initial_delta_beyond_frozen_tolerance_invalidates_pair():
    def mutate(document: dict) -> None:
        document["pairs"][0]["initial_state"]["arms"]["B"][
            "initial_tmean_c"
        ] = 25.0

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "INITIAL_TMEAN_DELTA_EXCEEDED" in result.pairs[0].reason_codes


def test_initial_gradient_beyond_frozen_tolerance_invalidates_pair():
    def mutate(document: dict) -> None:
        document["pairs"][0]["initial_state"]["arms"]["B"][
            "initial_gradient_c"
        ] = 1.0

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "INITIAL_GRADIENT_DELTA_EXCEEDED" in result.pairs[0].reason_codes


def test_unverified_initial_state_is_unresolved():
    def mutate(document: dict) -> None:
        document["pairs"][0]["initial_state"]["arms"]["B"][
            "initial_tmean_c"
        ] = None

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_UNRESOLVED
    assert "INITIAL_STATE_EVIDENCE_MISSING" in result.pairs[0].reason_codes


def test_open_door_at_start_invalidates_pair():
    def mutate(document: dict) -> None:
        document["pairs"][0]["initial_state"]["arms"]["B"]["door_state"] = "OPEN"

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_INVALID
    assert "DOOR_NOT_CLOSED_AT_START" in result.pairs[0].reason_codes


def test_invalid_attempt_without_reason_codes_is_refused():
    def mutate(document: dict) -> None:
        attempt = _attempt(document, "B")
        attempt["quality_status"] = "QUALITY_FAIL"
        attempt["validity_status"] = "INVALID"
        attempt["validity_reason_codes"] = []

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_undeclared_validity_reason_code_is_refused():
    def mutate(document: dict) -> None:
        attempt = _attempt(document, "B")
        attempt["quality_status"] = "QUALITY_FAIL"
        attempt["validity_status"] = "INVALID"
        attempt["validity_reason_codes"] = ["LOOKS_BAD"]

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_planned_pair_with_no_attempts_is_planned():
    def mutate(document: dict) -> None:
        document["attempts"] = []
        document["pairs"][0]["attempt_ids"] = []

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_PLANNED
    assert result.attempt_accounting.total_attempts == 0


def test_single_arm_awaits_the_second_arm():
    def mutate(document: dict) -> None:
        document["attempts"] = [
            attempt
            for attempt in document["attempts"]
            if attempt["controller_arm"] == "A"
        ]
        document["pairs"][0]["attempt_ids"] = ["ATT-TEST-001-A"]

    result = _mutated(mutate)
    assert result.pairs[0].status == PAIR_AWAITING_SECOND_ARM


def test_campaign_freeze_missing_is_reported_and_blocks_admission():
    assessment = assess_campaign_freeze(None)
    assert assessment.freeze_status == FREEZE_STATUS_MISSING
    assert assessment.physical_admission == "BLOCKED_MISSING_FREEZE"
    assert set(assessment.unfrozen_field_ids) == set(CAMPAIGN_FREEZE_FIELD_IDS)


def test_campaign_freeze_incomplete_records_unfrozen_fields():
    record = _campaign_freeze_record()
    record["fields"]["operating_threshold"] = {
        "value": 30.0,
        "provenance": "test://w19/fixture",
        "status": "DECLARED_NOT_VERIFIED",
    }
    assessment = assess_campaign_freeze(record)
    assert assessment.freeze_status == FREEZE_STATUS_INCOMPLETE
    assert "operating_threshold" in assessment.unfrozen_field_ids


def test_campaign_freeze_with_a_null_value_is_not_approved():
    record = _campaign_freeze_record()
    record["fields"]["operating_threshold"]["value"] = None
    assessment = assess_campaign_freeze(record)
    assert assessment.freeze_status == FREEZE_STATUS_INCOMPLETE
    assert "operating_threshold" in assessment.missing_field_ids


def test_campaign_freeze_field_without_provenance_is_not_approved():
    record = _campaign_freeze_record()
    record["fields"]["cooling_action_magnitude"]["provenance"] = ""
    assessment = assess_campaign_freeze(record)
    assert assessment.freeze_status == FREEZE_STATUS_INCOMPLETE
    assert "cooling_action_magnitude" in assessment.unfrozen_field_ids


def test_complete_campaign_freeze_is_approved():
    assessment = assess_campaign_freeze(_campaign_freeze_record())
    assert assessment.freeze_status == FREEZE_STATUS_APPROVED
    assert assessment.physical_admission == "ELIGIBLE_PENDING_AUTHORIZATION"


def test_campaign_freeze_drift_requires_human_comparability_decision():
    baseline = _campaign_freeze_record()
    observed = _campaign_freeze_record()
    observed["fields"]["operating_threshold"]["value"] = 31.0
    drift = compare_campaign_freeze(baseline, observed)
    assert drift.comparison_status == "DRIFT_DETECTED"
    assert drift.changed_fields == ("operating_threshold",)
    assert drift.comparability_decision == "HUMAN_COMPARABILITY_DETERMINATION_REQUIRED"
    assert drift.semantics_note == DEVELOPMENT_BASELINE_DOES_NOT_IMPLY_FREEZE


def test_identical_campaign_freeze_reports_no_drift():
    drift = compare_campaign_freeze(
        _campaign_freeze_record(), _campaign_freeze_record()
    )
    assert drift.comparison_status == "IDENTICAL"
    assert drift.changed_fields == ()


def test_attempt_identity_drift_marks_pair_unresolved():
    def mutate(document: dict) -> None:
        _attempt(document, "B")["model_artifact_sha256"] = hashlib.sha256(
            b"DIFFERENT-MODEL"
        ).hexdigest()

    document = _admitted_fixture()
    mutate(document)
    result = validate_pair_ledger(document)
    assert result.pairs[0].status == PAIR_UNRESOLVED
    assert "CAMPAIGN_IDENTITY_DRIFT" in result.pairs[0].reason_codes
    assert result.pairs[0].campaign_identity_drift_fields == (
        "model_artifact_sha256",
    )


def test_conflicting_target_count_sources_are_flagged():
    document = _admitted_fixture()
    document["campaign_freeze"]["fields"]["target_pair_count"]["value"] = "3"
    document["frozen_target"] = {
        "status": "FROZEN_APPROVED",
        "planned_pair_target": 2,
        "approval": {
            "authority_id": "TEST_FIXTURE_ONLY",
            "authority_role": "TEAM_LEAD",
            "canonical_ref": "test://w19/fixture-target",
        },
        "variance_justification_ref": "test://w19/fixture-variance",
    }
    result = validate_pair_ledger(document)
    assert result.target_count_conflict is True
    assert "PAIR_TARGET_COUNT_SOURCE_CONFLICT" in result.refusal_reasons
    assert not result.physical_pair_evidence_accepted


def test_correction_must_target_a_recorded_attempt_field():
    def mutate(document: dict) -> None:
        _attempt(document, "B")["corrections"] = [
            {
                "correction_id": "CORR-1",
                "field": "thermal_exposure",
                "previous_value": 10,
                "corrected_value": 11,
                "reason": "typo",
                "recorded_by": "operator",
            }
        ]

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_audit_event_detail_must_be_text():
    def mutate(document: dict) -> None:
        _attempt(document, "B")["audit_events"][0]["detail"] = {
            "peak_temp_c": 31.4
        }

    with pytest.raises(W19LedgerError):
        _mutated(mutate)


def test_physical_admission_requires_authorization_and_freeze():
    document = _admitted_fixture()
    result = validate_pair_ledger(document)
    assert result.pairs[0].status == PAIR_VALID
    assert result.physical_valid_pairs == 1
    assert result.physical_pair_evidence_accepted

    document = _admitted_fixture()
    document["campaign_authorization"]["g4_status"] = "NOT_READY"
    result = validate_pair_ledger(document)
    assert result.authorization["status"] == AUTHORIZATION_FAKE_APPROVAL
    assert result.physical_valid_pairs == 0


def test_authorization_state_machine():
    assert (
        evaluate_campaign_authorization(None).status == AUTHORIZATION_NOT_AUTHORIZED
    )
    record = {
        "authorized": True,
        "authority_id": "LEAD-1",
        "authority_role": "TEAM_LEAD",
        "canonical_ref": "test://lead-approval",
        "g4_status": "READY",
        "pair_target_frozen": True,
        "analysis_freeze_accepted": True,
    }
    assert evaluate_campaign_authorization(record).status == AUTHORIZATION_AUTHORIZED
    fake = dict(record)
    fake["authority_id"] = ""
    assert (
        evaluate_campaign_authorization(fake).status == AUTHORIZATION_FAKE_APPROVAL
    )
    fake = dict(record)
    fake["canonical_ref"] = ""
    assert (
        evaluate_campaign_authorization(fake).status == AUTHORIZATION_FAKE_APPROVAL
    )


def test_authorization_claim_with_red_g4_is_fake():
    record = {
        "authorized": True,
        "authority_id": "LEAD-1",
        "authority_role": "TEAM_LEAD",
        "canonical_ref": "test://lead-approval",
        "g4_status": "NOT_READY",
        "pair_target_frozen": True,
        "analysis_freeze_accepted": True,
    }
    assessment = evaluate_campaign_authorization(record)
    assert assessment.status == AUTHORIZATION_FAKE_APPROVAL
    assert "FAKE_APPROVAL:G4_NOT_READY" in assessment.refusal_reasons


def test_unknown_pair_field_is_rejected():
    def mutate(document: dict) -> None:
        document["pairs"][0]["outcome_definition"] = "unexpected"

    with pytest.raises(W19LedgerError):
        _mutated(mutate)
