"""W17 shadow exit report tests."""
import pytest

from coldguard_control.shadow import (
    FalsePolicyTransition,
    ShadowDecision,
    ShadowExitReport,
    ShadowExitStatus,
    ShadowTimingComparison,
    StaleStateIssue,
    UnresolvedAmbiguity,
    SafetyBlockReason,
    build_shadow_exit_report,
    compare_shadow_to_reactive,
    evaluate_shadow,
)
from coldguard_control.config import PolicyConfig
from coldguard_control.policy import PolicyInput


def test_false_policy_transition_validation():
    transition = FalsePolicyTransition(
        transition_id="t-001",
        from_state="NORMAL",
        to_state="PREEMPTIVE_COOLING",
        predicted_at_s=100.0,
        physical_state_unchanged=True,
        reason="Sensor noise triggered false transition",
    )
    assert transition.physical_state_unchanged is True


def test_stale_state_issue_validation():
    issue = StaleStateIssue(
        issue_id="s-001",
        state_age_at_decision_s=5.0,
        max_freshness_bound_s=2.0,
        decision_affected=True,
    )
    assert issue.decision_affected is True


def test_unresolved_ambiguity_validation():
    ambiguity = UnresolvedAmbiguity(
        ambiguity_id="a-001",
        ambiguity_type="CONFLICTING_SENSORS",
        affected_decision="PREEMPTIVE_COOLING",
        resolution_method="FALLBACK_TO_REACTIVE",
    )
    assert ambiguity.resolution_method == "FALLBACK_TO_REACTIVE"


def test_safety_block_reason_validation():
    block = SafetyBlockReason(
        block_id="b-001",
        safety_constraint="MAX_CURRENT_LIMIT",
        blocked_action="ON",
        block_justified=True,
    )
    assert block.block_justified is True


def test_shadow_exit_report_no_commands_emitted():
    """W17 invariant: total_commands_emitted must be 0."""
    report = ShadowExitReport(
        false_transitions=(),
        stale_state_issues=(),
        unresolved_ambiguities=(),
        safety_block_reasons=(),
        total_shadow_decisions=10,
        total_commands_emitted=0,
    )
    assert report.total_commands_emitted == 0

    with pytest.raises(ValueError, match="total_commands_emitted"):
        ShadowExitReport(
            false_transitions=(),
            stale_state_issues=(),
            unresolved_ambiguities=(),
            safety_block_reasons=(),
            total_shadow_decisions=10,
            total_commands_emitted=1,  # Not allowed
        )


def test_shadow_exit_report_exit_status_clean():
    report = ShadowExitReport(
        false_transitions=(),
        stale_state_issues=(),
        unresolved_ambiguities=(),
        safety_block_reasons=(),
        total_shadow_decisions=10,
    )
    assert report.exit_status is ShadowExitStatus.CLEAN_EXIT


def test_shadow_exit_report_exit_status_false_transition():
    transition = FalsePolicyTransition(
        transition_id="t-001",
        from_state="NORMAL",
        to_state="PREEMPTIVE_COOLING",
        predicted_at_s=100.0,
        physical_state_unchanged=True,
        reason="Sensor noise",
    )
    report = ShadowExitReport(
        false_transitions=(transition,),
        stale_state_issues=(),
        unresolved_ambiguities=(),
        safety_block_reasons=(),
        total_shadow_decisions=10,
    )
    assert report.exit_status is ShadowExitStatus.FALSE_TRANSITION_DETECTED


def test_shadow_exit_report_exit_status_stale_state():
    issue = StaleStateIssue(
        issue_id="s-001",
        state_age_at_decision_s=5.0,
        max_freshness_bound_s=2.0,
        decision_affected=True,
    )
    report = ShadowExitReport(
        false_transitions=(),
        stale_state_issues=(issue,),
        unresolved_ambiguities=(),
        safety_block_reasons=(),
        total_shadow_decisions=10,
    )
    assert report.exit_status is ShadowExitStatus.STALE_STATE_ISSUE


def test_shadow_exit_report_exit_status_unresolved_ambiguity():
    ambiguity = UnresolvedAmbiguity(
        ambiguity_id="a-001",
        ambiguity_type="CONFLICTING_SENSORS",
        affected_decision="PREEMPTIVE_COOLING",
        resolution_method="FALLBACK_TO_REACTIVE",
    )
    report = ShadowExitReport(
        false_transitions=(),
        stale_state_issues=(),
        unresolved_ambiguities=(ambiguity,),
        safety_block_reasons=(),
        total_shadow_decisions=10,
    )
    assert report.exit_status is ShadowExitStatus.UNRESOLVED_AMBIGUITY


def test_shadow_exit_report_exit_status_safety_blocked():
    block = SafetyBlockReason(
        block_id="b-001",
        safety_constraint="MAX_CURRENT_LIMIT",
        blocked_action="ON",
        block_justified=True,
    )
    report = ShadowExitReport(
        false_transitions=(),
        stale_state_issues=(),
        unresolved_ambiguities=(),
        safety_block_reasons=(block,),
        total_shadow_decisions=10,
    )
    assert report.exit_status is ShadowExitStatus.SAFETY_BLOCKED


def test_shadow_exit_report_exit_status_multiple_issues():
    transition = FalsePolicyTransition(
        transition_id="t-001",
        from_state="NORMAL",
        to_state="PREEMPTIVE_COOLING",
        predicted_at_s=100.0,
        physical_state_unchanged=True,
        reason="Sensor noise",
    )
    issue = StaleStateIssue(
        issue_id="s-001",
        state_age_at_decision_s=5.0,
        max_freshness_bound_s=2.0,
        decision_affected=True,
    )
    report = ShadowExitReport(
        false_transitions=(transition,),
        stale_state_issues=(issue,),
        unresolved_ambiguities=(),
        safety_block_reasons=(),
        total_shadow_decisions=10,
    )
    assert report.exit_status is ShadowExitStatus.MULTIPLE_ISSUES


def test_build_shadow_exit_report():
    """W17: build_shadow_exit_report ensures no commands emitted."""
    report = build_shadow_exit_report(
        false_transitions=[],
        stale_state_issues=[],
        unresolved_ambiguities=[],
        safety_block_reasons=[],
        total_shadow_decisions=10,
    )
    assert report.total_commands_emitted == 0


def test_compare_shadow_to_reactive():
    comparison = compare_shadow_to_reactive(
        shadow_at_s=100.0,
        reactive_at_s=105.0,
    )
    assert comparison.status == "ESTIMATED"
    assert comparison.lead_s == 5.0


def test_compare_shadow_to_reactive_not_estimable():
    comparison = compare_shadow_to_reactive(
        shadow_at_s=None,
        reactive_at_s=105.0,
    )
    assert comparison.status == "NOT_ESTIMABLE"
    assert comparison.lead_s is None


def test_compare_shadow_to_reactive_invalid_input():
    with pytest.raises(ValueError, match="timing anchors"):
        compare_shadow_to_reactive(
            shadow_at_s=float('inf'),
            reactive_at_s=105.0,
        )