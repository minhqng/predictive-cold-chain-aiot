"""W03 priority assertions: CRITICAL_PROTECTION > PREEMPTIVE, FAULT > optimization."""

from __future__ import annotations

import pytest

from _builders import (
    PLAIN_FAULT,
    make_config,
    make_input,
    make_prediction,
    make_thermal,
)
from coldguard_control import (
    ActuationIntent,
    ControllerId,
    CoolingState,
    ModelHealth,
    PolicyState,
    QualityState,
    ReasonCode,
    evaluate_policy,
)


def test_critical_protection_beats_fresh_predictive_warning() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.VALID, 9.0, 1.0),
            prediction=make_prediction(risk=0.99, persisted=600.0),
        ),
        cfg,
    )

    assert decision.state is PolicyState.CRITICAL_PROTECTION
    assert decision.actuation_intent is ActuationIntent.ON
    assert decision.controller_id is ControllerId.REACTIVE
    assert decision.reason_code is ReasonCode.THRESHOLD_HIGH


def test_predictive_only_warning_below_critical_boundary_is_preemptive() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.VALID, 7.0, 1.0),
            prediction=make_prediction(risk=0.95, persisted=120.0),
        ),
        cfg,
    )

    assert decision.state is PolicyState.PREEMPTIVE_COOLING
    assert decision.actuation_intent is ActuationIntent.ON
    assert decision.controller_id is ControllerId.PREDICTIVE
    assert decision.reason_code is ReasonCode.PREDICTED_CRITICAL


def test_plain_fault_beats_every_predictive_optimization() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.VALID, 7.0, 1.0),
            prediction=make_prediction(risk=0.99, persisted=600.0),
            fault_active=True,
            fault_reason=PLAIN_FAULT,
        ),
        cfg,
    )

    assert decision.state is PolicyState.FAULT
    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.reason_code is PLAIN_FAULT
    assert decision.predictive_blocked is True


def test_thermal_fault_blocks_optimization_even_when_prediction_is_fresh() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.INVALID, None, 1.0),
            prediction=make_prediction(risk=0.99, persisted=600.0),
        ),
        cfg,
    )

    assert decision.state is PolicyState.FAULT_LOCKOUT
    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.reason_code is ReasonCode.THERMAL_STATE_INVALID
    assert decision.predictive_blocked is True


def test_control_electrical_anomaly_beats_heat_and_prediction() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.VALID, 12.0, 1.0),
            prediction=make_prediction(risk=0.99, persisted=600.0),
            control_electrical_anomaly=True,
        ),
        cfg,
    )

    assert decision.state is PolicyState.FAULT_LOCKOUT
    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.reason_code is ReasonCode.CONTROL_ELECTRICAL_ANOMALY
    assert decision.predictive_blocked is True


def test_hardware_safety_condition_beats_heat_and_prediction() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.VALID, 12.0, 1.0),
            prediction=make_prediction(risk=0.99, persisted=600.0),
            hardware_safety_condition=True,
        ),
        cfg,
    )

    assert decision.state is PolicyState.FAULT_LOCKOUT
    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.reason_code is None
    assert "hardware safety" in decision.reason_detail
    assert decision.predictive_blocked is True


def test_lockout_class_fault_reason_escalates_from_fault_to_lockout() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(
            fault_active=True,
            fault_reason=ReasonCode.CONTROL_ELECTRICAL_ANOMALY,
        ),
        cfg,
    )

    assert decision.state is PolicyState.FAULT_LOCKOUT
    assert decision.actuation_intent is ActuationIntent.HOLD


def test_degraded_sensing_keeps_local_protection_priority() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.DEGRADED, 9.0, 1.0),
            prediction=make_prediction(risk=0.99, persisted=600.0),
        ),
        cfg,
    )

    assert decision.state is PolicyState.CRITICAL_PROTECTION
    assert decision.actuation_intent is ActuationIntent.ON
    assert decision.degraded_sensing is True
    assert decision.predictive_blocked is True


def test_stale_prediction_is_never_reused_for_actuation() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.VALID, 7.0, 1.0),
            prediction=make_prediction(risk=0.99, persisted=999.0, age=301.0),
        ),
        cfg,
    )

    assert decision.state is PolicyState.SAFE_LOCAL
    assert decision.actuation_intent is not ActuationIntent.ON
    assert decision.reason_code is ReasonCode.AI_UNAVAILABLE
    assert decision.predictive_blocked is True


def test_unavailable_model_blocks_preemptive_action() -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(
            prediction=make_prediction(
                risk=None,
                persisted=None,
                age=1.0,
                health=ModelHealth.UNAVAILABLE,
            )
        ),
        cfg,
    )

    assert decision.state is PolicyState.SAFE_LOCAL
    assert decision.reason_code is ReasonCode.AI_UNAVAILABLE
    assert decision.actuation_intent is not ActuationIntent.ON


def test_predictive_disabled_ignores_advisory_score() -> None:
    cfg = make_config(predictive_enabled=False)
    decision = evaluate_policy(
        make_input(
            thermal=make_thermal(QualityState.VALID, 7.0, 1.0),
            prediction=make_prediction(risk=0.99, persisted=999.0),
            applied_cooling=CoolingState.OFF,
        ),
        cfg,
    )

    assert decision.state is PolicyState.NORMAL
    assert decision.actuation_intent is ActuationIntent.HOLD
    assert decision.controller_id is ControllerId.REACTIVE
    assert decision.predictive_blocked is False


@pytest.mark.parametrize(
    ("risk", "persisted", "expected"),
    [
        (0.55, 0.0, PolicyState.WATCH),
        (0.75, 29.9, PolicyState.WATCH),
        (0.75, 30.0, PolicyState.PREEMPTIVE_COOLING),
    ],
)
def test_persistence_gate_separates_watch_from_preemptive(
    risk: float, persisted: float, expected: PolicyState
) -> None:
    cfg = make_config(predictive_enabled=True)
    decision = evaluate_policy(
        make_input(prediction=make_prediction(risk=risk, persisted=persisted)),
        cfg,
    )

    assert decision.state is expected
    if expected is PolicyState.WATCH:
        assert decision.actuation_intent is ActuationIntent.HOLD
        assert decision.controller_id is ControllerId.REACTIVE
    else:
        assert decision.actuation_intent is ActuationIntent.ON
        assert decision.controller_id is ControllerId.PREDICTIVE
