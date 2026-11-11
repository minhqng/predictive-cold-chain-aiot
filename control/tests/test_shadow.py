from coldguard_control import ModelHealth
from coldguard_control.shadow import compare_shadow_to_reactive, evaluate_shadow

from _builders import make_config, make_input, make_prediction


def predictive_config():
    return make_config(
        predictive_enabled=True,
        watch_threshold=0.5,
        preemptive_threshold=0.7,
        persistence_required_s=30.0,
        prediction_max_age_s=120.0,
    )


def test_shadow_is_deterministic_and_never_emits_command():
    policy_input = make_input(prediction=make_prediction())
    first = evaluate_shadow(policy_input, predictive_config())
    second = evaluate_shadow(policy_input, predictive_config())
    assert first == second
    assert first.physical_command_emitted is False
    assert first.decision_sha256 == second.decision_sha256


def test_stale_prediction_is_logged_as_blocked_not_reused():
    result = evaluate_shadow(
        make_input(prediction=make_prediction(age=121.0)), predictive_config()
    )
    assert result.policy_decision.predictive_blocked is True
    assert result.physical_command_emitted is False


def test_unavailable_prediction_is_blocked():
    result = evaluate_shadow(
        make_input(prediction=make_prediction(health=ModelHealth.UNAVAILABLE)),
        predictive_config(),
    )
    assert result.policy_decision.predictive_blocked is True


def test_timing_comparison_refuses_missing_anchor():
    assert compare_shadow_to_reactive(
        shadow_at_s=10.0, reactive_at_s=None
    ).status == "NOT_ESTIMABLE"
    estimated = compare_shadow_to_reactive(shadow_at_s=10.0, reactive_at_s=25.0)
    assert estimated.status == "ESTIMATED"
    assert estimated.lead_s == 15.0
