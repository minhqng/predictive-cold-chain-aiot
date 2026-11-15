from dataclasses import FrozenInstanceError

import pytest

from coldguard_control.campaign_audit import (
    AnomalyEntry,
    AuditAnomalyCategory,
    CampaignAuditRecord,
    CampaignEvidenceAuthority,
    G5Signoff,
    audit_campaign as audit_campaign_raw,
)
from coldguard_control.campaign_integrity import ControllerVariant


def record(controller=ControllerVariant.A, **overrides):
    values = {
        "run_id": "run-a-001" if controller is ControllerVariant.A else "run-b-001",
        "controller": controller,
        "policy_version": "a-v1" if controller is ControllerVariant.A else "b-v1",
        "valid": True,
        "prediction_present": True,
        "policy_trace_present": True,
        "command_present": True,
        "ack_present": True,
        "physical_verification_present": True,
        "reactive_trigger_correct": True,
        "rejected_command_reasons": (),
        "verification_failed": False,
        "safe_local_event_count": 0,
        "control_anomaly": False,
        # W20: New required fields
        "evidence_authority": CampaignEvidenceAuthority.LIVE_EVIDENCE,
        "policy_id": "policy-v1",
        "config_id": "config-v1",
        "action_id": "action-v1",
        "evidence_ref": "evidence/D/W20/live-run.json",
        "operator_identity": "member-D",
    }
    values.update(overrides)
    return CampaignAuditRecord(**values)


def b_record(**overrides):
    values = dict(run_id="run-b-001", controller=ControllerVariant.B, policy_version="b-v1")
    values.update(overrides)
    return record(**values)


SIGNOFF = G5Signoff(
    signer="member-D",
    signed_at="2026-11-12T10:00:00Z",
    evidence_ref="evidence/D/W20/g5-signoff.json",
)


def audit_campaign(records):
    return audit_campaign_raw(records, SIGNOFF)


def test_clean_campaign_audits_and_reaches_g5():
    decision = audit_campaign([record(ControllerVariant.A), record(ControllerVariant.B)])
    assert decision.audited_run_ids == ("run-a-001", "run-b-001")
    assert decision.excluded_invalid_run_ids == ()
    assert decision.audit_findings == ()
    assert decision.anomalies == ()
    assert decision.a_policy_versions == ("a-v1",)
    assert decision.b_policy_versions == ("b-v1",)
    assert decision.g5_ready is True
    assert decision.g5_blockers == ()
    assert decision.silently_corrected is False


def test_host_records_or_missing_signoff_cannot_reach_g5():
    host = [
        record(ControllerVariant.A, evidence_authority=CampaignEvidenceAuthority.HOST_SIMULATED,
               evidence_ref=None, operator_identity=None),
        record(ControllerVariant.B, evidence_authority=CampaignEvidenceAuthority.HOST_SIMULATED,
               evidence_ref=None, operator_identity=None),
    ]
    assert audit_campaign(host).g5_ready is False
    unsigned = audit_campaign_raw([record(ControllerVariant.A), record(ControllerVariant.B)])
    assert unsigned.g5_ready is False
    assert "G5_SIGNOFF_REQUIRED" in unsigned.g5_blockers


@pytest.mark.parametrize(
    ("field", "finding"),
    [
        ("prediction_present", "MISSING_PREDICTION"),
        ("policy_trace_present", "MISSING_POLICY_TRACE"),
        ("command_present", "MISSING_COMMAND"),
        ("ack_present", "MISSING_ACK"),
        ("physical_verification_present", "MISSING_PHYSICAL_VERIFICATION"),
    ],
)
def test_each_missing_b_evidence_item_flags_and_blocks_g5(field, finding):
    decision = audit_campaign(
        [record(ControllerVariant.A), b_record(**{field: False})]
    )
    assert f"run-b-001:{finding}" in decision.audit_findings
    assert decision.g5_ready is False
    assert any(blocker.startswith("NOT_ALL_VALID_RUNS_PASS") for blocker in decision.g5_blockers)


def test_incorrect_reactive_trigger_on_a_run_flags_and_blocks_g5():
    decision = audit_campaign(
        [record(ControllerVariant.A, reactive_trigger_correct=False), record(ControllerVariant.B)]
    )
    assert "run-a-001:INCORRECT_REACTIVE_TRIGGER" in decision.audit_findings
    assert decision.g5_ready is False


@pytest.mark.parametrize(
    ("field", "finding", "category"),
    [
        ("verification_failed", "VERIFICATION_FAILED", AuditAnomalyCategory.VERIFICATION_FAILURE),
        ("control_anomaly", "CONTROL_ANOMALY", AuditAnomalyCategory.CONTROL_ANOMALY),
    ],
)
def test_verification_failure_or_control_anomaly_on_valid_run_fails_it(field, finding, category):
    decision = audit_campaign(
        [record(ControllerVariant.A, **{field: True}), record(ControllerVariant.B)]
    )
    assert f"run-a-001:{finding}" in decision.audit_findings
    assert any(entry.category is category and entry.run_id == "run-a-001" for entry in decision.anomalies)
    assert decision.g5_ready is False


def test_invalid_runs_are_excluded_from_audit_but_listed():
    decision = audit_campaign(
        [
            record(ControllerVariant.A),
            record(ControllerVariant.B),
            b_record(run_id="run-b-002", valid=False, prediction_present=False, ack_present=False),
        ]
    )
    assert decision.audited_run_ids == ("run-a-001", "run-b-001")
    assert decision.excluded_invalid_run_ids == ("run-b-002",)
    assert decision.audit_findings == ()
    assert decision.g5_ready is True


def test_anomaly_report_lists_all_four_categories():
    decision = audit_campaign(
        [
            record(
                ControllerVariant.A,
                rejected_command_reasons=("COMMAND_EXPIRED", "COMMAND_OUT_OF_RANGE"),
                safe_local_event_count=2,
            ),
            b_record(verification_failed=True, control_anomaly=True),
        ]
    )
    by_category = {}
    for entry in decision.anomalies:
        by_category.setdefault(entry.category, []).append(entry)
    assert [e.detail for e in by_category[AuditAnomalyCategory.REJECTED_COMMAND]] == [
        "COMMAND_EXPIRED",
        "COMMAND_OUT_OF_RANGE",
    ]
    assert all(
        e.run_id == "run-a-001" for e in by_category[AuditAnomalyCategory.REJECTED_COMMAND]
    )
    assert by_category[AuditAnomalyCategory.VERIFICATION_FAILURE][0].run_id == "run-b-001"
    assert by_category[AuditAnomalyCategory.SAFE_LOCAL_EVENT][0].detail == "SAFE_LOCAL_EVENTS=2"
    assert by_category[AuditAnomalyCategory.CONTROL_ANOMALY][0].run_id == "run-b-001"
    assert len(by_category[AuditAnomalyCategory.CONTROL_ANOMALY]) == 1


def test_rejected_commands_and_safe_local_events_alone_do_not_block_g5():
    decision = audit_campaign(
        [
            record(
                ControllerVariant.A,
                rejected_command_reasons=("COMMAND_DUPLICATE",),
                safe_local_event_count=1,
            ),
            record(ControllerVariant.B),
        ]
    )
    assert decision.g5_ready is True
    assert len(decision.anomalies) == 2


@pytest.mark.parametrize(
    ("records", "blocker"),
    [
        ([record(ControllerVariant.A, valid=False), record(ControllerVariant.B)], "NO_VALID_CONTROLLER_A_RUN"),
        ([record(ControllerVariant.A), record(ControllerVariant.B, valid=False)], "NO_VALID_CONTROLLER_B_RUN"),
        ([record(ControllerVariant.B)], "NO_VALID_CONTROLLER_A_RUN"),
    ],
)
def test_g5_requires_at_least_one_valid_a_and_b_run(records, blocker):
    decision = audit_campaign(records)
    assert decision.g5_ready is False
    assert blocker in decision.g5_blockers


def test_multiple_policy_versions_for_one_controller_block_g5():
    decision = audit_campaign(
        [
            record(ControllerVariant.A),
            record(ControllerVariant.B),
            b_record(run_id="run-b-002", policy_version="b-v2"),
        ]
    )
    assert decision.b_policy_versions == ("b-v1", "b-v2")
    assert decision.g5_ready is False
    assert any(
        blocker.startswith("MULTIPLE_CONTROLLER_B_POLICY_VERSIONS")
        for blocker in decision.g5_blockers
    )


def test_policy_drift_in_invalid_run_still_blocks_g5():
    decision = audit_campaign(
        [
            record(ControllerVariant.A),
            record(ControllerVariant.B),
            b_record(run_id="run-b-002", valid=False, policy_version="b-drifted"),
        ]
    )
    assert decision.audit_findings == ()
    assert decision.g5_ready is False
    assert any(
        blocker.startswith("MULTIPLE_CONTROLLER_B_POLICY_VERSIONS")
        for blocker in decision.g5_blockers
    )


def test_record_types_are_strict():
    with pytest.raises(ValueError, match="run_id"):
        record(run_id="")
    with pytest.raises(TypeError, match="strict boolean"):
        record(valid=1)
    with pytest.raises(TypeError, match="strict boolean"):
        record(prediction_present=0)
    with pytest.raises(ValueError, match="safe_local_event_count"):
        record(safe_local_event_count=True)
    with pytest.raises(ValueError, match="safe_local_event_count"):
        record(safe_local_event_count=-1)
    with pytest.raises(TypeError, match="rejected_command_reasons"):
        record(rejected_command_reasons="COMMAND_EXPIRED")
    with pytest.raises(ValueError, match="rejected_command_reasons"):
        record(rejected_command_reasons=("ok", "  "))


def test_anomaly_entry_types_are_strict():
    with pytest.raises(TypeError, match="AuditAnomalyCategory"):
        AnomalyEntry(category="REJECTED_COMMAND", run_id="run-1", detail="COMMAND_EXPIRED")
    with pytest.raises(ValueError, match="run_id"):
        AnomalyEntry(AuditAnomalyCategory.REJECTED_COMMAND, "", "COMMAND_EXPIRED")
    with pytest.raises(ValueError, match="detail"):
        AnomalyEntry(AuditAnomalyCategory.REJECTED_COMMAND, "run-1", "")


def test_audit_input_is_strict():
    with pytest.raises(ValueError, match="non-empty"):
        audit_campaign([])
    with pytest.raises(TypeError, match="Sequence"):
        audit_campaign("not-a-sequence")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Sequence"):
        audit_campaign({"run_id": "run-a-001"})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="CampaignAuditRecord"):
        audit_campaign([record(ControllerVariant.A), object()])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="duplicate run_id"):
        audit_campaign([record(ControllerVariant.A), record(ControllerVariant.A)])


def test_records_and_entries_are_immutable():
    evidence = record(ControllerVariant.A)
    with pytest.raises(FrozenInstanceError):
        evidence.policy_version = "changed"  # type: ignore[misc]
    decision = audit_campaign([record(ControllerVariant.A), record(ControllerVariant.B)])
    with pytest.raises(FrozenInstanceError):
        decision.g5_ready = False  # type: ignore[misc]
