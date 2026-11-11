import pytest

from coldguard_control.enablement import (
    EnablementDecision,
    EnablementPreconditions,
    EnablementStatus,
    evaluate_physical_enablement,
)


def all_preconditions(**overrides) -> EnablementPreconditions:
    values = {
        "enable_requested": True,
        "g4_green": True,
        "a_physical_envelope_stable": True,
        "b_model_frozen": True,
        "b_policy_frozen": True,
        "b_action_frozen": True,
        "c_command_trace_stable": True,
        "complete_prediction_to_thermal_trace": True,
        "failure_behavior_frozen": True,
        "clean_dry_runs_verified": True,
        "witness_member_a": True,
        "witness_member_b": True,
        "witness_member_c": True,
        "witness_member_d": True,
    }
    values.update(overrides)
    return EnablementPreconditions(**values)


def test_disabled_when_enable_not_requested():
    preconditions = all_preconditions(enable_requested=False)
    decision = evaluate_physical_enablement(preconditions)
    assert decision.status is EnablementStatus.DISABLED
    assert decision.review_ready is False
    assert decision.physical_command_emitted is False
    assert decision.blockers == ()


def test_review_ready_when_requested_and_all_preconditions_met():
    preconditions = all_preconditions(enable_requested=True)
    decision = evaluate_physical_enablement(preconditions)
    assert decision.status is EnablementStatus.REVIEW_READY
    assert decision.review_ready is True
    assert decision.physical_command_emitted is False
    assert decision.blockers == ()


@pytest.mark.parametrize(
    "missing_flag",
    [
        "g4_green",
        "a_physical_envelope_stable",
        "b_model_frozen",
        "b_policy_frozen",
        "b_action_frozen",
        "c_command_trace_stable",
        "complete_prediction_to_thermal_trace",
        "failure_behavior_frozen",
        "clean_dry_runs_verified",
        "witness_member_a",
        "witness_member_b",
        "witness_member_c",
        "witness_member_d",
    ],
)
def test_blocked_when_any_documented_precondition_missing(missing_flag: str):
    preconditions = all_preconditions(**{missing_flag: False})
    decision = evaluate_physical_enablement(preconditions)
    assert decision.status is EnablementStatus.BLOCKED
    assert decision.review_ready is False
    assert decision.physical_command_emitted is False
    assert missing_flag in decision.blockers


def test_never_emits_physical_command():
    # In all states (disabled, blocked, review_ready), physical_command_emitted must strictly be False
    for req in (False, True):
        for flag in (False, True):
            decision = evaluate_physical_enablement(
                all_preconditions(enable_requested=req, g4_green=flag)
            )
            assert decision.physical_command_emitted is False


def test_strict_boolean_type_validation():
    # Numeric 1 or 0, strings, or None must be rejected
    with pytest.raises(TypeError, match="must be a strict boolean"):
        all_preconditions(enable_requested=1)

    with pytest.raises(TypeError, match="must be a strict boolean"):
        all_preconditions(g4_green="True")

    with pytest.raises(TypeError, match="must be a strict boolean"):
        all_preconditions(b_model_frozen=None)


def test_preconditions_type_validation():
    with pytest.raises(TypeError, match="preconditions must be EnablementPreconditions"):
        evaluate_physical_enablement({"enable_requested": True})  # type: ignore[arg-type]
