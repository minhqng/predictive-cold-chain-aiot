"""W19 B-W19-04 frozen-target progress accounting controls."""

from __future__ import annotations

import copy
import hashlib

import pytest

from coldguard_ml.w19_no_peeking import FREEZE_FROZEN_APPROVED
from coldguard_ml.w19_pair_ledger import (
    CAMPAIGN_FREEZE_FIELD_IDS,
    EVIDENCE_PHYSICAL_CAMPAIGN,
    FAILURE_INVALIDATE_PAIR,
    W19LedgerError,
    build_test_only_fixture_ledger,
    validate_pair_ledger,
)
from coldguard_ml.w19_progress import (
    FIRST_WAVE_NOT_COMPUTABLE,
    FIRST_WAVE_NOT_REACHED,
    FIRST_WAVE_REACHED,
    PROGRESS_ESTABLISHED,
    PROGRESS_NOT_ESTABLISHED,
    TARGET_CHANGE_ACCEPTED_REQUIRES_NEW_FREEZE,
    TARGET_CHANGE_NONE,
    TARGET_CHANGE_REFUSED_MISSING_APPROVAL,
    TARGET_CHANGE_REFUSED_POST_CAMPAIGN_START,
    TARGET_FROZEN,
    TARGET_INVALID,
    TARGET_NOT_APPROVED,
    TARGET_PROGRESS_COMPLETE,
    TARGET_PROGRESS_NOT_COMPUTABLE,
    TARGET_UNKNOWN_UNFROZEN,
    assess_pair_target,
    assess_target_change,
    compute_campaign_progress,
)

MODEL_SHA = hashlib.sha256(b"W19-FIXTURE-MODEL-ARTIFACT").hexdigest()


def _approval() -> dict:
    return {
        "authority_id": "TEST_FIXTURE_ONLY",
        "authority_role": "TEAM_LEAD",
        "canonical_ref": "test://w19/fixture-target",
    }


def _target(pairs: int = 2, **overrides) -> dict:
    record = {
        "status": FREEZE_FROZEN_APPROVED,
        "planned_pair_target": pairs,
        "approval": _approval(),
        "variance_justification_ref": "test://w19/fixture-variance",
    }
    record.update(overrides)
    return record


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
    document = build_test_only_fixture_ledger()
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


def _append_admitted_pair(document: dict) -> None:
    pair = copy.deepcopy(document["pairs"][0])
    pair["pair_id"] = "PAIR-TEST-002"
    pair["attempt_ids"] = []
    for arm in ("A", "B"):
        source = next(
            attempt
            for attempt in document["attempts"]
            if attempt["controller_arm"] == arm
        )
        attempt = copy.deepcopy(source)
        attempt["pair_id"] = "PAIR-TEST-002"
        attempt["attempt_id"] = f"ATT-TEST-002-{arm}"
        attempt["run_id"] = f"RUN-TEST-002-{arm}"
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


def _invalid_arm(document: dict, arm: str = "B") -> None:
    attempt = next(
        item for item in document["attempts"] if item["controller_arm"] == arm
    )
    attempt["quality_status"] = "QUALITY_FAIL"
    attempt["validity_status"] = "INVALID"
    attempt["validity_reason_codes"] = ["PHYSICAL_QUALITY_INVALID"]


def test_missing_target_is_unknown_and_remaining_is_not_computable():
    progress = compute_campaign_progress(
        validate_pair_ledger(build_test_only_fixture_ledger()),
        target_record=None,
    )
    assert progress.pair_target_freeze_status == TARGET_UNKNOWN_UNFROZEN
    assert progress.planned_pair_target is None
    assert progress.remaining_target == "NOT_COMPUTABLE"
    assert progress.target_progress_status == TARGET_PROGRESS_NOT_COMPUTABLE
    assert progress.first_wave_status == FIRST_WAVE_NOT_COMPUTABLE


def test_unfrozen_target_record_stays_unknown():
    record = _target(4, status="PROVISIONAL")
    assert assess_pair_target(record).status == TARGET_UNKNOWN_UNFROZEN


def test_zero_negative_and_non_integer_targets_are_invalid():
    assert assess_pair_target(_target(0)).status == TARGET_INVALID
    assert assess_pair_target(_target(-2)).status == TARGET_INVALID
    assert assess_pair_target(_target(2.5)).status == TARGET_INVALID
    assert assess_pair_target(_target(True)).status == TARGET_INVALID


def test_target_without_approval_is_not_approved():
    record = _target(4)
    record["approval"] = None
    assert assess_pair_target(record).status == TARGET_NOT_APPROVED
    record = _target(4)
    record["approval"] = {"authority_id": "", "authority_role": "TEAM_LEAD"}
    assert assess_pair_target(record).status == TARGET_NOT_APPROVED


def test_rough_sample_size_estimate_is_not_an_approved_target():
    record = _target(16)
    record["approval"] = None
    record["variance_justification_ref"] = "ml/scripts/sample_size_planning.py"
    assessment = assess_pair_target(record)
    assert assessment.status == TARGET_NOT_APPROVED
    assert assessment.planned_pair_target is None


def test_target_without_variance_justification_is_not_approved():
    record = _target(16, variance_justification_ref=None)
    assert assess_pair_target(record).status == TARGET_NOT_APPROVED


def test_synthetic_fixture_never_contributes_progress():
    progress = compute_campaign_progress(
        validate_pair_ledger(build_test_only_fixture_ledger()),
        target_record=_target(2),
    )
    assert progress.valid_pairs_completed == 0
    assert progress.software_validated_pairs == 1
    assert progress.valid_pair_progress_status == PROGRESS_NOT_ESTABLISHED
    assert progress.physical_campaign_status == "NOT_STARTED_BLOCKED"
    assert progress.remaining_target == "NOT_COMPUTABLE"
    assert progress.first_wave_status == FIRST_WAVE_NOT_COMPUTABLE


def test_physical_campaign_unauthorized_is_not_started_blocked():
    document = _admitted_fixture()
    document["campaign_authorization"]["authorized"] = False
    progress = compute_campaign_progress(
        validate_pair_ledger(document), target_record=_target(2)
    )
    assert progress.campaign_authorization_status == "NOT_AUTHORIZED"
    assert progress.physical_campaign_status == "NOT_STARTED_BLOCKED"
    assert progress.valid_pair_progress_status == PROGRESS_NOT_ESTABLISHED
    assert progress.valid_pairs_completed == 0
    assert progress.remaining_target == "NOT_COMPUTABLE"


def test_fake_authorization_blocks_progress():
    document = _admitted_fixture()
    document["campaign_authorization"]["authority_id"] = ""
    progress = compute_campaign_progress(
        validate_pair_ledger(document), target_record=_target(2)
    )
    assert progress.campaign_authorization_status == "FAKE_APPROVAL_DETECTED"
    assert progress.physical_campaign_status == "NOT_STARTED_BLOCKED"
    assert progress.valid_pairs_completed == 0


def test_one_of_two_frozen_pairs_progresses():
    progress = compute_campaign_progress(
        validate_pair_ledger(_admitted_fixture()), target_record=_target(2)
    )
    assert progress.valid_pairs_completed == 1
    assert progress.remaining_target == 1
    assert progress.target_progress_status == "IN_PROGRESS"
    assert progress.first_wave_status == FIRST_WAVE_REACHED
    assert progress.first_wave_fraction == 0.5
    assert progress.valid_pair_progress_status == PROGRESS_ESTABLISHED


def test_first_wave_not_reached_below_half_of_frozen_target():
    progress = compute_campaign_progress(
        validate_pair_ledger(_admitted_fixture()), target_record=_target(4)
    )
    assert progress.remaining_target == 3
    assert progress.first_wave_status == FIRST_WAVE_NOT_REACHED
    assert progress.first_wave_fraction == 0.25


def test_target_reached_is_complete_and_pending_lock():
    progress = compute_campaign_progress(
        validate_pair_ledger(_admitted_fixture()), target_record=_target(1)
    )
    assert progress.valid_pairs_completed == 1
    assert progress.remaining_target == 0
    assert progress.target_progress_status == TARGET_PROGRESS_COMPLETE
    assert progress.physical_campaign_status == "TARGET_REACHED_PENDING_LOCK"
    assert progress.target_overshoot_pairs == 0


def test_target_overshoot_is_reported_not_hidden():
    document = _admitted_fixture()
    _append_admitted_pair(document)
    progress = compute_campaign_progress(
        validate_pair_ledger(document), target_record=_target(1)
    )
    assert progress.valid_pairs_completed == 2
    assert progress.remaining_target == 0
    assert progress.target_overshoot_pairs == 1


def test_invalid_pairs_are_not_counted_as_complete():
    document = _admitted_fixture()
    _invalid_arm(document)
    document["failure_policy"]["invalid_arm_handling"] = FAILURE_INVALIDATE_PAIR
    progress = compute_campaign_progress(
        validate_pair_ledger(document), target_record=_target(2)
    )
    assert progress.valid_pairs_completed == 0
    assert progress.invalid_pairs == 1
    assert progress.pairs_started == 1
    assert progress.remaining_target == 2
    assert progress.physical_campaign_status == "IN_PROGRESS"


def test_invalid_attempts_are_reported_separately_from_invalid_pairs():
    document = _admitted_fixture()
    _invalid_arm(document)
    progress = compute_campaign_progress(validate_pair_ledger(document))
    assert progress.invalid_attempts == 1
    assert progress.invalid_pairs == 0
    assert progress.unresolved_pairs == 1


def test_repeated_attempts_inside_one_pair_do_not_inflate_progress():
    document = _admitted_fixture()
    original = next(
        attempt
        for attempt in document["attempts"]
        if attempt["controller_arm"] == "B"
    )
    original["quality_status"] = "QUALITY_FAIL"
    original["validity_status"] = "INVALID"
    original["validity_reason_codes"] = ["PHYSICAL_QUALITY_INVALID"]
    rerun = copy.deepcopy(original)
    rerun["attempt_id"] = "ATT-TEST-001-B-R1"
    rerun["run_id"] = "RUN-TEST-001-B-R1"
    rerun["attempt_kind"] = "RERUN"
    rerun["supersedes"] = original["attempt_id"]
    rerun["quality_status"] = "QUALITY_PASS"
    rerun["validity_status"] = "VALID"
    rerun["validity_reason_codes"] = []
    rerun["source_sha256"] = hashlib.sha256(b"rerun-B").hexdigest()
    rerun["source_path"] = "test://w19/fixture/run-B-rerun"
    original["superseded_by"] = rerun["attempt_id"]
    original["audit_events"] = original["audit_events"] + [
        {"seq": 3, "event": "ATTEMPT_SUPERSEDED", "actor": "test-fixture"}
    ]
    document["attempts"].append(rerun)
    document["pairs"][0]["attempt_ids"].append(rerun["attempt_id"])
    result = validate_pair_ledger(document)
    progress = compute_campaign_progress(result, target_record=_target(2))
    assert result.attempt_accounting.total_attempts == 3
    assert progress.valid_pairs_completed == 1
    assert progress.remaining_target == 1


def test_one_pair_cannot_be_counted_twice():
    document = _admitted_fixture()
    document["pairs"].append(copy.deepcopy(document["pairs"][0]))
    with pytest.raises(W19LedgerError):
        validate_pair_ledger(document)


def test_unavailable_attempt_ledger_is_unknown_not_zero():
    progress = compute_campaign_progress(None)
    assert progress.invalid_attempts is None
    assert progress.invalid_attempts_status == "UNKNOWN_ATTEMPT_LEDGER_UNAVAILABLE"
    assert progress.valid_pairs_completed == 0
    assert progress.valid_pair_progress_status == "NOT_ESTABLISHED"
    assert progress.target_progress_status == "NOT_COMPUTABLE"


def test_synthetic_ledger_cannot_establish_progress_even_with_authorization():
    document = build_test_only_fixture_ledger()
    document["campaign_authorization"] = {
        "authorized": True,
        "authority_id": "TEST_FIXTURE_ONLY",
        "authority_role": "TEAM_LEAD",
        "canonical_ref": "test://w19/fixture-authorization",
        "g4_status": "READY",
        "pair_target_frozen": True,
        "analysis_freeze_accepted": True,
    }
    progress = compute_campaign_progress(
        validate_pair_ledger(document), target_record=_target(2)
    )
    assert progress.campaign_authorization_status == "AUTHORIZED"
    assert progress.physical_evidence_class == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert progress.valid_pair_progress_status == PROGRESS_NOT_ESTABLISHED
    assert progress.physical_campaign_status == "NOT_STARTED_BLOCKED"
    assert progress.remaining_target == "NOT_COMPUTABLE"


def test_conflicting_target_sources_make_progress_non_computable():
    document = _admitted_fixture()
    document["campaign_freeze"]["fields"]["target_pair_count"]["value"] = "3"
    target = _target(2)
    document["frozen_target"] = target
    progress = compute_campaign_progress(
        validate_pair_ledger(document), target_record=target
    )
    assert progress.pair_target_source_conflict is True
    assert progress.remaining_target == "NOT_COMPUTABLE"
    assert progress.target_progress_status == TARGET_PROGRESS_NOT_COMPUTABLE
    assert progress.first_wave_status == FIRST_WAVE_NOT_COMPUTABLE


def test_target_change_after_pairs_recorded_is_refused():
    decision = assess_target_change(
        None, _target(4), valid_pairs_completed=1
    )
    assert decision.decision == TARGET_CHANGE_REFUSED_POST_CAMPAIGN_START


def test_target_change_with_recorded_but_invalid_pairs_is_refused():
    decision = assess_target_change(
        None,
        _target(4),
        valid_pairs_completed=0,
        pairs_recorded=3,
    )
    assert decision.decision == TARGET_CHANGE_REFUSED_POST_CAMPAIGN_START


def test_target_change_before_start_requires_approval_then_new_freeze():
    missing = assess_target_change(
        None, _target(4, approval=None), valid_pairs_completed=0
    )
    assert missing.decision == TARGET_CHANGE_REFUSED_MISSING_APPROVAL
    accepted = assess_target_change(None, _target(4), valid_pairs_completed=0)
    assert accepted.decision == TARGET_CHANGE_ACCEPTED_REQUIRES_NEW_FREEZE


def test_identical_target_is_not_a_change():
    decision = assess_target_change(_target(4), _target(4), valid_pairs_completed=1)
    assert decision.decision == TARGET_CHANGE_NONE
