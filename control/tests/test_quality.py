"""W05 physical-quality input contract tests (05D D-W05-01/02/03/04).

These tests prove that the quality assessment layer:
* never treats UNKNOWN as healthy (Doc 01 section 19.4);
* requires explicit freshness bounds (no hidden constants);
* separates thermal safety usability from prediction availability;
* classifies missing electrical evidence without inventing root causes.
"""

from __future__ import annotations

import pytest

from coldguard_control import (
    ChannelObservation,
    QualityAssessment,
    QualityInputError,
    QualityState,
    ReasonCode,
    assess_quality,
)

SYNTHETIC_MAX_AGE = 15.0
SYNTHETIC_ELECTRICAL_MAX_AGE = 10.0
SYNTHETIC_DOOR_MAX_AGE = 5.0


def _thermal(
    quality: QualityState = QualityState.VALID,
    age: float | None = 1.0,
) -> ChannelObservation:
    return ChannelObservation(quality=quality, age_s=age)


def _electrical(
    quality: QualityState = QualityState.VALID,
    age: float | None = 1.0,
) -> ChannelObservation:
    return ChannelObservation(quality=quality, age_s=age)


def _door(
    quality: QualityState = QualityState.UNKNOWN,
    age: float | None = 1.0,
) -> ChannelObservation:
    return ChannelObservation(quality=quality, age_s=age)


def test_all_fresh_valid_is_predictive_available() -> None:
    result = assess_quality(
        thermal=_thermal(QualityState.VALID, 1.0),
        electrical=_electrical(QualityState.VALID, 1.0),
        door=_door(QualityState.VALID, 1.0),
        thermal_max_age_s=SYNTHETIC_MAX_AGE,
        electrical_max_age_s=SYNTHETIC_ELECTRICAL_MAX_AGE,
        door_max_age_s=SYNTHETIC_DOOR_MAX_AGE,
    )

    assert result.thermal_safety_usable is True
    assert result.predictive_inputs_available is True
    assert result.verification_confidence is QualityState.VALID
    assert result.blockers == ()


def test_unknown_thermal_is_not_treated_as_healthy() -> None:
    result = assess_quality(
        thermal=_thermal(QualityState.UNKNOWN, None),
        electrical=_electrical(QualityState.VALID, 1.0),
        door=_door(QualityState.VALID, 1.0),
        thermal_max_age_s=SYNTHETIC_MAX_AGE,
        electrical_max_age_s=SYNTHETIC_ELECTRICAL_MAX_AGE,
        door_max_age_s=SYNTHETIC_DOOR_MAX_AGE,
    )

    assert result.thermal_safety_usable is False
    assert result.predictive_inputs_available is False
    assert result.verification_confidence is QualityState.UNKNOWN
    assert any(b.channel == "thermal" for b in result.blockers)


def test_stale_thermal_is_not_control_fresh() -> None:
    result = assess_quality(
        thermal=_thermal(QualityState.VALID, 20.0),
        electrical=_electrical(QualityState.VALID, 1.0),
        door=_door(QualityState.VALID, 1.0),
        thermal_max_age_s=SYNTHETIC_MAX_AGE,
        electrical_max_age_s=SYNTHETIC_ELECTRICAL_MAX_AGE,
        door_max_age_s=SYNTHETIC_DOOR_MAX_AGE,
    )

    assert result.thermal_safety_usable is False
    assert result.predictive_inputs_available is False


def test_degraded_thermal_keeps_safety_usable() -> None:
    result = assess_quality(
        thermal=_thermal(QualityState.DEGRADED, 1.0),
        electrical=_electrical(QualityState.VALID, 1.0),
        door=_door(QualityState.VALID, 1.0),
        thermal_max_age_s=SYNTHETIC_MAX_AGE,
        electrical_max_age_s=SYNTHETIC_ELECTRICAL_MAX_AGE,
        door_max_age_s=SYNTHETIC_DOOR_MAX_AGE,
    )

    assert result.thermal_safety_usable is True
    assert result.predictive_inputs_available is False
    assert result.verification_confidence is QualityState.DEGRADED
    assert any(b.channel == "thermal" for b in result.blockers)


def test_missing_electrical_is_unknown_not_invalid() -> None:
    result = assess_quality(
        thermal=_thermal(QualityState.VALID, 1.0),
        electrical=_electrical(QualityState.UNKNOWN, None),
        door=_door(QualityState.VALID, 1.0),
        thermal_max_age_s=SYNTHETIC_MAX_AGE,
        electrical_max_age_s=SYNTHETIC_ELECTRICAL_MAX_AGE,
        door_max_age_s=SYNTHETIC_DOOR_MAX_AGE,
    )

    assert result.thermal_safety_usable is True
    assert result.predictive_inputs_available is False
    assert result.verification_confidence is QualityState.UNKNOWN
    blockers = [b for b in result.blockers if b.channel == "electrical"]
    assert len(blockers) == 1
    assert blockers[0].reason_code is ReasonCode.PZEM_UNAVAILABLE


def test_invalid_electrical_is_control_invalid() -> None:
    result = assess_quality(
        thermal=_thermal(QualityState.VALID, 1.0),
        electrical=_electrical(QualityState.INVALID, None),
        door=_door(QualityState.VALID, 1.0),
        thermal_max_age_s=SYNTHETIC_MAX_AGE,
        electrical_max_age_s=SYNTHETIC_ELECTRICAL_MAX_AGE,
        door_max_age_s=SYNTHETIC_DOOR_MAX_AGE,
    )

    assert result.thermal_safety_usable is True
    assert result.predictive_inputs_available is False
    assert result.verification_confidence is QualityState.INVALID


def test_door_never_defaults_to_closed() -> None:
    result = assess_quality(
        thermal=_thermal(QualityState.VALID, 1.0),
        electrical=_electrical(QualityState.VALID, 1.0),
        door=_door(QualityState.UNKNOWN, None),
        thermal_max_age_s=SYNTHETIC_MAX_AGE,
        electrical_max_age_s=SYNTHETIC_ELECTRICAL_MAX_AGE,
        door_max_age_s=SYNTHETIC_DOOR_MAX_AGE,
    )

    assert result.predictive_inputs_available is False
    blockers = [b for b in result.blockers if b.channel == "door"]
    assert len(blockers) == 1
    assert "never treated as CLOSED" in blockers[0].detail


def test_age_without_bound_is_not_fresh() -> None:
    result = assess_quality(
        thermal=_thermal(QualityState.VALID, 1.0),
        electrical=_electrical(QualityState.VALID, 1.0),
        door=_door(QualityState.VALID, 1.0),
        thermal_max_age_s=SYNTHETIC_MAX_AGE,
        electrical_max_age_s=None,
        door_max_age_s=None,
    )

    assert result.thermal_safety_usable is True
    assert result.predictive_inputs_available is False
    assert result.verification_confidence is QualityState.UNKNOWN


def test_negative_age_is_rejected() -> None:
    with pytest.raises(QualityInputError, match="cannot be negative"):
        assess_quality(
            thermal=_thermal(QualityState.VALID, -1.0),
            electrical=_electrical(QualityState.VALID, 1.0),
            door=_door(QualityState.VALID, 1.0),
            thermal_max_age_s=SYNTHETIC_MAX_AGE,
            electrical_max_age_s=SYNTHETIC_ELECTRICAL_MAX_AGE,
            door_max_age_s=SYNTHETIC_DOOR_MAX_AGE,
        )


def test_non_finite_age_is_rejected() -> None:
    with pytest.raises(QualityInputError, match="must be a finite number"):
        assess_quality(
            thermal=_thermal(QualityState.VALID, float("nan")),
            electrical=_electrical(QualityState.VALID, 1.0),
            door=_door(QualityState.VALID, 1.0),
            thermal_max_age_s=SYNTHETIC_MAX_AGE,
            electrical_max_age_s=SYNTHETIC_ELECTRICAL_MAX_AGE,
            door_max_age_s=SYNTHETIC_DOOR_MAX_AGE,
        )


def test_non_enum_quality_is_rejected() -> None:
    with pytest.raises(QualityInputError, match="must be a QualityState"):
        assess_quality(
            thermal=ChannelObservation(quality="VALID", age_s=1.0),
            electrical=_electrical(QualityState.VALID, 1.0),
            door=_door(QualityState.VALID, 1.0),
            thermal_max_age_s=SYNTHETIC_MAX_AGE,
            electrical_max_age_s=SYNTHETIC_ELECTRICAL_MAX_AGE,
            door_max_age_s=SYNTHETIC_DOOR_MAX_AGE,
        )


def test_verification_confidence_collapses_correctly() -> None:
    for thermal_q, electrical_q, expected in [
        (QualityState.VALID, QualityState.VALID, QualityState.VALID),
        (QualityState.DEGRADED, QualityState.VALID, QualityState.DEGRADED),
        (QualityState.VALID, QualityState.DEGRADED, QualityState.DEGRADED),
        (QualityState.INVALID, QualityState.VALID, QualityState.INVALID),
        (QualityState.VALID, QualityState.INVALID, QualityState.INVALID),
        (QualityState.UNKNOWN, QualityState.VALID, QualityState.UNKNOWN),
    ]:
        result = assess_quality(
            thermal=_thermal(thermal_q, 1.0),
            electrical=_electrical(electrical_q, 1.0),
            door=_door(QualityState.VALID, 1.0),
            thermal_max_age_s=SYNTHETIC_MAX_AGE,
            electrical_max_age_s=SYNTHETIC_ELECTRICAL_MAX_AGE,
            door_max_age_s=SYNTHETIC_DOOR_MAX_AGE,
        )
        assert result.verification_confidence is expected, (
            f"{thermal_q} + {electrical_q} -> {expected}"
        )
