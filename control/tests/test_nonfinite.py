"""Fail-closed regression tests for non-finite numeric inputs.

Review follow-up: Python comparisons against NaN are always false, so an
unguarded check like ``age > max_age`` or ``stable_s < required_s`` silently
passes and treats a broken value as trustworthy. These tests lock rejection at
every boundary touched by that class of bug:

* ``PolicyConfig`` required/optional numerics (NaN / +inf / -inf / bool);
* ``PolicyInput`` thermal, prediction and remote timing values;
* the standalone ``safe_local_exit_status`` gate (must never look satisfied);
* ``validate_command`` state freshness.

All numeric values are synthetic and introduce no physical bound.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from _builders import (
    EXPECTED_DEVICE,
    NOW_S,
    make_command,
    make_config,
    make_evidence,
    make_input,
    make_prediction,
    make_remote,
    make_thermal,
)
from coldguard_control import (
    AckStatus,
    ActuationIntent,
    ConfigError,
    DeviceMode,
    PolicyInputError,
    PolicyState,
    QualityState,
    ReasonCode,
    evaluate_policy,
    safe_local_exit_status,
    validate_command,
)

NON_FINITE = [math.nan, math.inf, -math.inf]

REQUIRED_NUMERIC_FIELDS = [
    "upper_on_c",
    "lower_off_c",
    "thermal_max_age_s",
    "command_max_future_skew_s",
    "broker_offline_grace_s",
    "backend_state_max_age_s",
    "safe_local_exit_min_stable_s",
]

OPTIONAL_NUMERIC_FIELDS = [
    "watch_threshold",
    "preemptive_threshold",
    "persistence_required_s",
    "prediction_max_age_s",
]


# ---------------------------------------------------------------------------
# 1. PolicyConfig
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("field", REQUIRED_NUMERIC_FIELDS)
@pytest.mark.parametrize("value", NON_FINITE)
def test_required_config_number_must_be_finite(field: str, value: float) -> None:
    with pytest.raises(ConfigError):
        make_config(**{field: value})


@pytest.mark.parametrize("field", REQUIRED_NUMERIC_FIELDS)
def test_required_config_number_rejects_bool(field: str) -> None:
    with pytest.raises(ConfigError):
        make_config(**{field: True})


@pytest.mark.parametrize("field", OPTIONAL_NUMERIC_FIELDS)
@pytest.mark.parametrize("value", NON_FINITE)
def test_optional_config_number_must_be_finite(field: str, value: float) -> None:
    # Validated even while the predictive path is disabled, so a latent
    # non-finite value cannot be activated later without review.
    with pytest.raises(ConfigError):
        make_config(**{field: value})


@pytest.mark.parametrize("field", ["allowed_duty_min", "allowed_duty_max"])
@pytest.mark.parametrize("value", NON_FINITE)
def test_duty_bounds_must_be_finite(field: str, value: float) -> None:
    values: dict[str, object] = {
        "allow_pwm_duty": True,
        "allowed_duty_min": 0.2,
        "allowed_duty_max": 0.8,
    }
    values[field] = value
    with pytest.raises(ConfigError):
        make_config(**values)


def test_boolean_flags_reject_non_boolean_values() -> None:
    with pytest.raises(ConfigError):
        make_config(predictive_enabled=1)
    with pytest.raises(ConfigError):
        make_config(allow_pwm_duty=0)


# ---------------------------------------------------------------------------
# 2. PolicyInput
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", NON_FINITE)
def test_thermal_value_must_be_finite(value: float) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(thermal=make_thermal(QualityState.VALID, value, 1.0)),
            make_config(),
        )


@pytest.mark.parametrize("value", NON_FINITE)
def test_thermal_age_must_be_finite(value: float) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(thermal=make_thermal(QualityState.VALID, 7.0, value)),
            make_config(),
        )


@pytest.mark.parametrize("value", NON_FINITE)
def test_prediction_risk_must_be_finite(value: float) -> None:
    cfg = make_config(predictive_enabled=True)
    prediction = dataclasses.replace(make_prediction(), risk_score=value)
    with pytest.raises(PolicyInputError):
        evaluate_policy(make_input(prediction=prediction), cfg)


@pytest.mark.parametrize("value", NON_FINITE)
def test_prediction_age_must_be_finite(value: float) -> None:
    cfg = make_config(predictive_enabled=True)
    with pytest.raises(PolicyInputError):
        evaluate_policy(make_input(prediction=make_prediction(age=value)), cfg)


@pytest.mark.parametrize("value", NON_FINITE)
def test_prediction_horizon_must_be_finite(value: float) -> None:
    cfg = make_config(predictive_enabled=True)
    prediction = dataclasses.replace(make_prediction(), horizon_s=value)
    with pytest.raises(PolicyInputError):
        evaluate_policy(make_input(prediction=prediction), cfg)


@pytest.mark.parametrize("value", NON_FINITE)
def test_prediction_persistence_must_be_finite(value: float) -> None:
    cfg = make_config(predictive_enabled=True)
    prediction = dataclasses.replace(
        make_prediction(), above_preemptive_s=value
    )
    with pytest.raises(PolicyInputError):
        evaluate_policy(make_input(prediction=prediction), cfg)


@pytest.mark.parametrize(
    "field",
    ["broker_offline_s", "backend_state_age_s", "network_stable_s"],
)
@pytest.mark.parametrize("value", NON_FINITE)
def test_remote_timing_must_be_finite(field: str, value: float) -> None:
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(remote=make_remote(**{field: value})), make_config()
        )


# ---------------------------------------------------------------------------
# 3. SAFE_LOCAL exit gate (called directly, without _validate_input)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", NON_FINITE)
def test_safe_local_exit_never_satisfied_by_nonfinite_network_stable(
    value: float,
) -> None:
    ok, missing = safe_local_exit_status(
        make_input(remote=make_remote(network_stable_s=value)), make_config()
    )
    assert ok is False
    assert "network_stable" in missing


@pytest.mark.parametrize("value", NON_FINITE)
def test_safe_local_exit_never_satisfied_by_nonfinite_backend_age(
    value: float,
) -> None:
    ok, missing = safe_local_exit_status(
        make_input(remote=make_remote(backend_state_age_s=value)),
        make_config(),
    )
    assert ok is False
    assert "backend_state_fresh" in missing


@pytest.mark.parametrize("value", NON_FINITE)
def test_safe_local_exit_never_satisfied_by_nonfinite_thermal_age(
    value: float,
) -> None:
    ok, missing = safe_local_exit_status(
        make_input(thermal=make_thermal(QualityState.VALID, 7.0, value)),
        make_config(),
    )
    assert ok is False
    assert "fresh_valid_telemetry" in missing


def test_nonfinite_remote_is_rejected_before_exit_evaluation() -> None:
    # The full policy path rejects the input outright rather than evaluating a
    # SAFE_LOCAL exit against a broken timing value.
    with pytest.raises(PolicyInputError):
        evaluate_policy(
            make_input(
                device_mode=DeviceMode.SAFE_LOCAL,
                current_state=PolicyState.SAFE_LOCAL,
                remote=make_remote(network_stable_s=math.nan),
            ),
            make_config(),
        )


# ---------------------------------------------------------------------------
# 4. Command state freshness
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, -1.0])
def test_command_state_freshness_rejects_nonfinite_or_negative_age(
    value: float,
) -> None:
    decision = validate_command(
        make_command(),
        make_evidence(thermal_age_s=value),
        make_config(),
        now_s=NOW_S,
        expected_device_id=EXPECTED_DEVICE,
        processed={},
    )
    assert decision.status is AckStatus.INVALID_STATE
    assert decision.reason_code is ReasonCode.COMMAND_STATE_STALE
    assert decision.may_actuate is False
    assert decision.actuation_intent is ActuationIntent.HOLD
