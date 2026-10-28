"""B <-> C contract regressions for normalized observations.

The audit found three mismatches between the backend wire contract and the ML
``Observation`` validator:

* backend ``run_id`` is nullable (pre-experiment samples) but ML required a
  non-empty string;
* DS18B20 (-55..125 C) and BME280 (-40..85 C) measure below zero, but ML
  rejected every negative temperature;
* the backend accepts only ``schema_version=1``, while ML accepted any value.

``uptime_ms`` is covered too: it stays optional in ML (normalized storage does
not carry it yet) but must be a valid monotonic counter when present.

All values are synthetic test values.
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import replace

import pytest

from coldguard_ml import (
    DataContractError,
    Observation,
    canonical_order,
    deduplicate_by_identity,
    rows_by_run,
    validate_observation,
)

UTC = _dt.timezone.utc
WHEN = _dt.datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)


def make_observation(**overrides: object) -> Observation:
    base = Observation(
        device_id="cg-test-001",
        boot_id="cg-test-001-boot-001",
        seq=0,
        time=WHEN,
        uptime_ms=1_000,
        run_id="CG-S1-A-001",
        t1_c=7.0,
        t2_c=7.1,
        t3_c=6.9,
        t_air_c=8.0,
        rh_pct=45.0,
        door_state="CLOSED",
        cooling_voltage_v=12.0,
        cooling_current_a=3.0,
        cooling_power_w=36.0,
        cooling_energy_counter_wh=1.0,
        applied_cooling="ON",
        applied_duty=0.6,
        thermal_quality="VALID",
        environment_quality="VALID",
        electrical_quality="VALID",
        overall_quality="VALID",
        device_mode="ONLINE_NORMAL",
        schema_version=1,
        hardware_config_id="CG-HW-001",
        firmware_version="fw-synthetic",
        calibration_id="CG-CAL-001",
    )
    return replace(base, **overrides)


# ---------------------------------------------------------------------------
# run_id: nullable at the boundary, but never in a run-based pipeline
# ---------------------------------------------------------------------------
def test_pre_experiment_sample_without_run_is_valid() -> None:
    observation = make_observation(run_id=None)

    validate_observation(observation)
    assert observation.run_id is None
    assert deduplicate_by_identity((observation,)) == (observation,)


def test_run_id_must_be_non_empty_when_present() -> None:
    with pytest.raises(DataContractError, match="run_id"):
        validate_observation(make_observation(run_id="   "))


def test_run_based_order_rejects_sample_without_run_association() -> None:
    with pytest.raises(DataContractError, match="run association"):
        canonical_order((make_observation(run_id=None),))


def test_row_grouping_rejects_sample_without_run_association() -> None:
    with pytest.raises(DataContractError, match="run association"):
        rows_by_run((make_observation(run_id=None),))


def test_run_association_is_required_for_trajectory_key() -> None:
    with pytest.raises(DataContractError, match="run association"):
        _ = make_observation(run_id=None).trajectory_key


# ---------------------------------------------------------------------------
# Temperature: negative values are physical on both sensors
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", [-10.5, -0.1, -55.0, 0.0, 125.0])
def test_ds18b20_temperature_range_is_accepted(value: float) -> None:
    validate_observation(
        make_observation(t1_c=value, t2_c=value, t3_c=value)
    )


@pytest.mark.parametrize("value", [-5.0, -40.0, 0.0, 85.0])
def test_bme280_air_temperature_range_is_accepted(value: float) -> None:
    validate_observation(make_observation(t_air_c=value))


@pytest.mark.parametrize("value", [-55.1, 125.1, math.nan, math.inf, -math.inf])
def test_ds18b20_out_of_range_or_non_finite_is_rejected(value: float) -> None:
    with pytest.raises(DataContractError, match="finite|range"):
        validate_observation(make_observation(t1_c=value))


@pytest.mark.parametrize("value", [-40.1, 85.1, math.nan, math.inf])
def test_bme280_out_of_range_or_non_finite_is_rejected(value: float) -> None:
    with pytest.raises(DataContractError, match="finite|range"):
        validate_observation(make_observation(t_air_c=value))


@pytest.mark.parametrize(
    "field", ["cooling_voltage_v", "cooling_current_a", "cooling_power_w", "cooling_energy_counter_wh"]
)
def test_required_non_negative_electrical_channels_stay_non_negative(
    field: str,
) -> None:
    with pytest.raises(DataContractError, match=">= 0"):
        validate_observation(make_observation(**{field: -0.01}))


def test_electrical_nan_is_rejected() -> None:
    with pytest.raises(DataContractError, match="finite"):
        validate_observation(make_observation(cooling_current_a=math.nan))


# ---------------------------------------------------------------------------
# schema_version: only supported versions, exact integer type
# ---------------------------------------------------------------------------
def test_supported_schema_version_is_accepted() -> None:
    validate_observation(make_observation(schema_version=1))


@pytest.mark.parametrize("value", [99, 0, -1, True, False, "1", 1.0, None])
def test_unsupported_or_wrong_type_schema_version_is_rejected(value: object) -> None:
    with pytest.raises(DataContractError, match="schema_version"):
        validate_observation(make_observation(schema_version=value))


# ---------------------------------------------------------------------------
# uptime_ms: optional in ML, but a real counter when present
# ---------------------------------------------------------------------------
def test_missing_uptime_is_accepted_but_invalid_counters_are_not() -> None:
    validate_observation(make_observation(uptime_ms=None))
    validate_observation(make_observation(uptime_ms=0))

    for value in (-1, True, 1.5, "1000"):
        with pytest.raises(DataContractError, match="uptime_ms"):
            validate_observation(make_observation(uptime_ms=value))


# ---------------------------------------------------------------------------
# Existing quality contract must stay strict
# ---------------------------------------------------------------------------
def test_valid_thermal_section_still_requires_every_value() -> None:
    with pytest.raises(DataContractError, match="VALID thermal"):
        validate_observation(make_observation(t3_c=None))
