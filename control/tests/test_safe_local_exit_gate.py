"""Regression: the SAFE_LOCAL exit gate is authoritative regardless of mode.

The audit found a fail-open path: ``device_mode=ONLINE_NORMAL`` with
``current_state=SAFE_LOCAL`` skipped the exit gate entirely because only the
device mode was consulted. With otherwise trusted remote evidence, predictive
enabled and a persistent high risk, the policy returned
``PREEMPTIVE_COOLING/ON`` even though ``network_stable_s=0`` and
``stale_command_pending=True``.

All numeric values are synthetic test values; they exercise branch logic only
and carry no commissioning authority.
"""

from __future__ import annotations

import pytest

from _builders import (
    PLAIN_FAULT,
    make_config,
    make_input,
    make_prediction,
    make_remote,
    make_thermal,
)
from coldguard_control import (
    ActuationIntent,
    ControllerId,
    DeviceMode,
    PolicyState,
    QualityState,
    evaluate_policy,
)


def test_predictive_cannot_bypass_gate_when_policy_state_is_safe_local() -> None:
    """Exact audit combination: ONLINE_NORMAL + SAFE_LOCAL + gate unmet."""

    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.ONLINE_NORMAL,
            current_state=PolicyState.SAFE_LOCAL,
            remote=make_remote(network_stable_s=0.0, stale_command_pending=True),
            prediction=make_prediction(),
        ),
        make_config(predictive_enabled=True),
    )

    assert decision.state is PolicyState.SAFE_LOCAL
    assert decision.actuation_intent is not ActuationIntent.ON
    assert "network_stable" in decision.safe_local_exit_missing
    assert "no_stale_command" in decision.safe_local_exit_missing


def test_mode_and_policy_state_disagreement_fails_closed() -> None:
    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.ONLINE_NORMAL,
            current_state=PolicyState.SAFE_LOCAL,
            remote=make_remote(network_stable_s=0.0),
        ),
        make_config(),
    )

    assert decision.state is PolicyState.SAFE_LOCAL
    assert decision.actuation_intent is not ActuationIntent.ON
    assert "network_stable" in decision.safe_local_exit_missing


@pytest.mark.parametrize(
    ("remote_overrides", "missing"),
    [
        ({"network_stable_s": 0.0}, "network_stable"),
        ({"stale_command_pending": True}, "no_stale_command"),
        (
            {"network_stable_s": 0.0, "stale_command_pending": True},
            "network_stable",
        ),
    ],
)
def test_unstable_network_or_unresolved_stale_command_holds_safe_local(
    remote_overrides: dict[str, object], missing: str
) -> None:
    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.ONLINE_NORMAL,
            current_state=PolicyState.SAFE_LOCAL,
            remote=make_remote(**remote_overrides),
        ),
        make_config(),
    )

    assert decision.state is PolicyState.SAFE_LOCAL
    assert missing in decision.safe_local_exit_missing


def test_safe_local_gate_also_applies_when_device_mode_declares_it() -> None:
    """The device-mode branch must keep working (normal SAFE_LOCAL case)."""

    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.SAFE_LOCAL,
            current_state=PolicyState.SAFE_LOCAL,
            remote=make_remote(network_stable_s=0.0),
            prediction=make_prediction(),
        ),
        make_config(predictive_enabled=True),
    )

    assert decision.state is PolicyState.SAFE_LOCAL
    assert decision.transition is None
    assert "network_stable" in decision.safe_local_exit_missing


def test_valid_exit_gate_allows_predictive_after_safe_local() -> None:
    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.ONLINE_NORMAL,
            current_state=PolicyState.SAFE_LOCAL,
            remote=make_remote(network_stable_s=120.0),
            prediction=make_prediction(),
        ),
        make_config(predictive_enabled=True),
    )

    assert decision.state is PolicyState.PREEMPTIVE_COOLING
    assert decision.actuation_intent is ActuationIntent.ON
    assert decision.transition == "SAFE_LOCAL_EXIT"


def test_valid_exit_with_predictive_disabled_falls_to_reactive() -> None:
    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.ONLINE_NORMAL,
            current_state=PolicyState.SAFE_LOCAL,
            remote=make_remote(network_stable_s=120.0),
            thermal=make_thermal(QualityState.VALID, 7.0, 1.0),
        ),
        make_config(),
    )

    assert decision.state is PolicyState.NORMAL
    assert decision.transition == "SAFE_LOCAL_EXIT"
    assert decision.controller_id is ControllerId.REACTIVE


def test_fault_and_lockout_priority_still_dominates_safe_local_gate() -> None:
    fault = evaluate_policy(
        make_input(
            device_mode=DeviceMode.ONLINE_NORMAL,
            current_state=PolicyState.SAFE_LOCAL,
            fault_active=True,
            fault_reason=PLAIN_FAULT,
        ),
        make_config(),
    )
    lockout = evaluate_policy(
        make_input(
            device_mode=DeviceMode.ONLINE_NORMAL,
            current_state=PolicyState.SAFE_LOCAL,
            control_electrical_anomaly=True,
        ),
        make_config(),
    )

    assert fault.state is PolicyState.FAULT
    assert fault.actuation_intent is ActuationIntent.HOLD
    assert lockout.state is PolicyState.FAULT_LOCKOUT
    assert lockout.actuation_intent is ActuationIntent.HOLD


def test_critical_thermal_protection_still_acts_inside_safe_local_regime() -> None:
    """Controller A reactive protection is allowed; predictive is not."""

    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.ONLINE_NORMAL,
            current_state=PolicyState.SAFE_LOCAL,
            remote=make_remote(network_stable_s=0.0),
            thermal=make_thermal(QualityState.VALID, 9.0, 1.0),
        ),
        make_config(),
    )

    assert decision.state is PolicyState.CRITICAL_PROTECTION
    assert decision.actuation_intent is ActuationIntent.ON
    assert decision.controller_id is ControllerId.REACTIVE


def test_gate_is_not_bypassed_by_predictive_disabled() -> None:
    decision = evaluate_policy(
        make_input(
            device_mode=DeviceMode.ONLINE_NORMAL,
            current_state=PolicyState.SAFE_LOCAL,
            remote=make_remote(network_stable_s=0.0, stale_command_pending=True),
        ),
        make_config(predictive_enabled=False),
    )

    assert decision.state is PolicyState.SAFE_LOCAL
    assert decision.actuation_intent is not ActuationIntent.ON
