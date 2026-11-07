"""W09 B0/B1 adversarial tests (Doc 05B §37, task §14 items 1-22)."""

from __future__ import annotations

import dataclasses
import math
import sys
from pathlib import Path

import pytest

from coldguard_ml import load_capture
from coldguard_ml.baselines import (
    B1_HYSTERESIS,
    B1_PERSISTENCE_CANDIDATE,
    CERTAINTY_BEFORE,
    CERTAINTY_EXACT,
    CERTAINTY_GAP,
    EVALUABILITY_DIAGNOSTIC,
    EVALUABILITY_REFUSED,
    INITIAL_OFF,
    INITIAL_ON,
    INITIAL_UNAVAILABLE,
    OPERATOR_GE,
    OPERATOR_GT,
    PersistenceCandidateConfig,
    REFUSAL_MIXED_BOOT,
    REFUSAL_TIME_DOMAIN,
    REPRESENTATIVE_MAX,
    REPRESENTATIVE_MEAN,
    REPRESENTATIVE_SINGLE,
    STATUS_EXPLORATORY,
    STATUS_SYNTHETIC,
    SAMPLE_DUPLICATE,
    SAMPLE_INVALID_QUALITY,
    SAMPLE_MISSING_VALUE,
    SAMPLE_NONFINITE,
    SAMPLE_STALE,
    STATE_OFF,
    STATE_ON,
    TRANSITION_CRITERION,
    TRANSITION_OFF,
    TRANSITION_ON,
    ThresholdConfig,
    ThermalQualityPolicy,
    HysteresisConfig,
    RepresentativeTemperature,
    controller_a_hysteresis_intent,
    evaluate_b0,
    evaluate_b1,
    representative_value,
)
from coldguard_ml.intake import (
    Capture,
    NormalizedRow,
    ProbeReading,
    RunIdentity,
    SensorRole,
    SourceIdentity,
    TimeSemantics,
)

import os

REPO_ROOT = Path(
    os.environ.get("W09_REPO_ROOT", Path(__file__).resolve().parents[2])
)
ML_ROOT = REPO_ROOT / "ml"
REAL_A_EXPORT = REPO_ROOT / "evidence/A/W09/exports/CG-S1-H8C-600S.json"
REAL_A_INDEX = REPO_ROOT / "evidence/A/W09/s1-run-index.json"

ROLES = {
    "t1": ("CHAMBER_CENTER", True),
    "t2": ("TEC_HOT_SIDE", False),
    "t3": ("CHAMBER_BOTTOM", True),
    "t4": ("CHAMBER_NEAR_DOOR", True),
}


def _probe(slot: str, value, *, status: str | None = "OK", age_ms=10):
    position, _ = ROLES[slot]
    return ProbeReading(
        slot=slot,
        value_c=value,
        status=status,
        role="HOT_SIDE" if slot == "t2" else "UNASSIGNED",
        age_ms=age_ms,
        rom=f"ROM-{slot}",
        physical_position=position,
    )


def _row(
    index: int,
    value: float,
    *,
    boot_id: str = "boot-1",
    run_id: str | None = "RUN-1",
    device_id: str | None = "dev-1",
    time_ms: int | None = None,
    thermal_quality: str = "VALID",
    applied: str = "OFF",
    skip_slots: tuple[str, ...] = (),
    probe_values: dict[str, object] | None = None,
    probe_status: str | None = "OK",
    age_ms=10,
    dedup_key=None,
):
    probe_values = probe_values or {}
    probes = []
    for slot in ("t1", "t2", "t3", "t4"):
        if slot in skip_slots:
            continue
        if slot in probe_values:
            probe_value = probe_values[slot]
        elif slot == "t1":
            probe_value = value
        elif slot == "t2":
            probe_value = 45.0
        elif slot == "t3":
            probe_value = value - 0.1
        else:
            probe_value = value + 0.1
        probes.append(_probe(slot, probe_value, status=probe_status, age_ms=age_ms))
    return NormalizedRow(
        seq=index + 1,
        boot_id=boot_id,
        run_id=run_id,
        device_id=device_id,
        hardware_config_id="HW-1",
        firmware_version="fw-1",
        device_ms=time_ms if time_ms is not None else index * 1000,
        event_time_utc=None,
        host_capture_time_utc=None,
        probes=tuple(probes),
        t_air_c=value,
        rh_pct=None,
        pressure_hpa=None,
        door_state="CLOSED",
        door_polarity=None,
        cooling_voltage_v=None,
        cooling_current_a=None,
        cooling_power_w=None,
        cooling_energy_counter_wh=None,
        electrical_measured_fields=(),
        applied_cooling=applied,
        applied_duty=None,
        applied_duty_permille=None,
        requested_duty_permille=None,
        readback_duty_permille=None,
        device_state=None,
        experiment_phase=None,
        quality=(
            ("thermal", thermal_quality),
            ("producer", "VALID"),
            ("overall", "VALID"),
        ),
        overall_quality="VALID",
        producer_quality="VALID",
        usable_for=("S1",),
        invalidation_reasons=(),
        source_line_index=index + 2,
        dedup_key=dedup_key or (boot_id, str(index + 1)),
    )


def _sensor_roles(*, unknown: tuple[str, ...] = ()) -> tuple[SensorRole, ...]:
    roles = []
    for slot in ("t1", "t2", "t3", "t4"):
        position, in_air = ROLES[slot]
        if slot in unknown:
            position = None
            in_air = None
        roles.append(
            SensorRole(
                slot=slot,
                rom=f"ROM-{slot}",
                rom_source="READBACK",
                rom_readback_verified=True,
                physical_position=position,
                position_source="DECLARED",
                in_chamber_air_aggregate=in_air,
                exclusion_reason=None if in_air else "HOT_SIDE",
                raw_roles=(slot.upper(),),
                role_conflict=None,
            )
        )
    return tuple(roles)


def _capture(
    values,
    *,
    rows=None,
    boot_id: str = "boot-1",
    sensor_roles: tuple[SensorRole, ...] | None = None,
    **row_kwargs,
) -> Capture:
    rows = rows if rows is not None else [
        _row(index, value, boot_id=boot_id, **row_kwargs)
        for index, value in enumerate(values)
    ]
    return Capture(
        source=SourceIdentity(
            path="synthetic-w09.json",
            sha256="a" * 64,
            format="A_W09_EXPORT",
            schema_namespace="coldguard.a",
            provenance="SYNTHETIC",
            is_physical_measurement=False,
        ),
        run=RunIdentity(
            run_id="RUN-1",
            run_id_status="RESOLVED",
            run_ids=("RUN-1",),
            boot_id=boot_id,
            boot_id_status="SOURCE_CARRIED",
            device_id="dev-1",
            device_id_status="RESOLVED",
            hardware_config_id="HW-1",
            hardware_config_status="VERIFIED",
            firmware_version="fw-1",
            firmware_version_status="RESOLVED",
            calibration_id="CAL-1",
            calibration_status="VERIFIED",
            scenario_id="S1",
            scenario_status="DECLARED",
            controller_id="OBSERVATIONAL",
            controller_status="DECLARED",
            device_run_label=None,
        ),
        time=TimeSemantics(
            domain="BOOT_SCOPED_UPTIME",
            event_time_status="UNAVAILABLE",
            clock_sync="SYNTHETIC_EXACT",
            boot_scoped=True,
            cross_boot_join_allowed=False,
            absolute_latency_supported=False,
            detail="synthetic",
        ),
        rows=tuple(rows),
        sensors=sensor_roles or _sensor_roles(),
        a_validity=None,
    )


def _representation(
    *,
    mode: str = REPRESENTATIVE_MEAN,
    slots: tuple[str, ...] = ("t1", "t3", "t4"),
    unit: str = "degC",
) -> RepresentativeTemperature:
    return RepresentativeTemperature(
        name="SYNTHETIC_REP",
        mode=mode,
        slots=slots,
        unit=unit,
        source="synthetic test",
        freeze_status=STATUS_SYNTHETIC,
    )


QUALITY = ThermalQualityPolicy(max_probe_age_s=5.0)


def _b0(
    *,
    threshold=30.0,
    operator=OPERATOR_GE,
    max_gap=5.0,
    representation=None,
    quality=QUALITY,
    time_domain="BOOT_SCOPED_UPTIME",
) -> ThresholdConfig:
    return ThresholdConfig(
        representation=representation or _representation(),
        threshold_c=threshold,
        operator=operator,
        time_domain=time_domain,
        quality=quality,
        threshold_source="synthetic",
        threshold_status=STATUS_SYNTHETIC,
        max_continuity_gap_s=max_gap,
        run_id="RUN-1",
        scenario_id="S1",
    )


def _b1(
    *,
    upper=30.0,
    lower=28.0,
    initial=INITIAL_OFF,
    max_gap=5.0,
    representation=None,
    quality=QUALITY,
    time_domain="BOOT_SCOPED_UPTIME",
) -> HysteresisConfig:
    return HysteresisConfig(
        representation=representation or _representation(),
        upper_on_c=upper,
        lower_off_c=lower,
        initial_state=initial,
        initial_state_source="synthetic initial state",
        time_domain=time_domain,
        quality=quality,
        upper_lower_source="synthetic",
        freeze_status=STATUS_SYNTHETIC,
        max_continuity_gap_s=max_gap,
        run_id="RUN-1",
        scenario_id="S1",
        policy_version="synthetic-policy-v1",
    )


# ---------------------------------------------------------------------------
# B0 — threshold semantics
# ---------------------------------------------------------------------------


def test_b0_threshold_equality_uses_declared_operator():
    capture = _capture([29.0, 30.0, 29.0])
    ge = evaluate_b0(capture, _b0(threshold=30.0, operator=OPERATOR_GE))
    gt = evaluate_b0(capture, _b0(threshold=30.0, operator=OPERATOR_GT))
    assert len(ge.criterion_crossings()) == 1
    assert ge.criterion_crossings()[0].time_certainty == CERTAINTY_EXACT
    assert ge.criterion_crossings()[0].time_s == 1.0
    assert ge.criterion_crossings()[0].crossing_time_s == 1.0
    assert gt.criterion_crossings() == ()


def test_b0_just_below_and_above_threshold():
    capture = _capture([29.999, 30.001])
    plan = evaluate_b0(capture, _b0())
    assert len(plan.criterion_crossings()) == 1
    assert plan.criterion_crossings()[0].time_s == 1.0


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), -float("inf"), True, "30"])
def test_b0_rejects_nonfinite_bool_and_malformed_values(bad_value):
    rows = [
        _row(0, 29.0),
        _row(1, 29.0, probe_values={"t1": bad_value}),
        _row(2, 31.0),
    ]
    capture = _capture([], rows=rows)
    result = evaluate_b0(capture, _b0())
    bad_samples = [
        sample
        for sample in result.samples
        if sample.sample_status in (SAMPLE_NONFINITE, SAMPLE_MISSING_VALUE)
    ]
    assert bad_samples
    assert all(sample.representative_c is None for sample in bad_samples)
    assert len(result.criterion_crossings()) == 1
    assert result.criterion_crossings()[0].time_certainty == CERTAINTY_GAP


def test_b0_missing_representative_probe_is_not_substituted():
    capture = _capture([29.0, 30.0], skip_slots=("t4",))
    result = evaluate_b0(capture, _b0())
    assert result.transitions == ()
    assert all(
        sample.sample_status == SAMPLE_MISSING_VALUE for sample in result.samples
    )


@pytest.mark.parametrize(
    "representation",
    [
        _representation(mode=REPRESENTATIVE_SINGLE, slots=("t2",)),
        _representation(mode=REPRESENTATIVE_MEAN, slots=("t1", "t2", "t3")),
        _representation(mode=REPRESENTATIVE_MAX, slots=("t2", "t3")),
    ],
)
def test_b0_rejects_hot_side_in_chamber_air_aggregate(representation):
    capture = _capture([30.0])
    with pytest.raises(Exception):
        evaluate_b0(capture, _b0(representation=representation))


def test_b0_rejects_unknown_sensor_roles():
    capture = _capture([30.0], sensor_roles=_sensor_roles(unknown=("t3",)))
    with pytest.raises(Exception):
        evaluate_b0(capture, _b0())


def test_b0_invalid_quality_is_not_a_substituted_value():
    rows = [
        _row(0, 29.0),
        _row(1, 31.0, thermal_quality="INVALID"),
        _row(2, 31.0),
    ]
    capture = _capture([], rows=rows)
    result = evaluate_b0(capture, _b0())
    assert any(
        sample.sample_status == SAMPLE_INVALID_QUALITY for sample in result.samples
    )
    assert len(result.criterion_crossings()) == 1
    crossing = result.criterion_crossings()[0]
    assert crossing.time_certainty == CERTAINTY_GAP
    assert crossing.crossing_interval_start_s == 0.0
    assert crossing.crossing_interval_end_s == 2.0


def test_b0_gap_crossing_has_no_invented_precise_time():
    rows = [
        _row(0, 29.0, time_ms=0),
        _row(1, 29.0, time_ms=1000),
        _row(2, 31.0, time_ms=10000),
    ]
    capture = _capture([], rows=rows)
    result = evaluate_b0(capture, _b0(max_gap=5.0))
    crossing = result.criterion_crossings()[0]
    assert crossing.time_certainty == CERTAINTY_GAP
    assert crossing.crossing_interval_start_s == 1.0
    assert crossing.crossing_interval_end_s == 10.0
    assert crossing.crossing_time_s is None
    assert result.coverage.gap_count == 1


def test_b0_mixed_boot_sessions_are_refused():
    rows = [
        _row(0, 29.0, boot_id="boot-1"),
        _row(1, 31.0, boot_id="boot-2"),
    ]
    capture = _capture([], rows=rows, boot_id="boot-1")
    result = evaluate_b0(capture, _b0())
    assert result.evaluability == EVALUABILITY_REFUSED
    assert result.refusal_reason == REFUSAL_MIXED_BOOT


def test_b0_duplicate_delivery_does_not_create_a_second_crossing():
    rows = [
        _row(0, 29.0),
        _row(1, 30.0),
        _row(1, 30.0, dedup_key=("boot-1", "2")),
        _row(2, 30.0),
        _row(3, 30.0),
    ]
    capture = _capture([], rows=rows)
    result = evaluate_b0(capture, _b0())
    assert len(result.criterion_crossings()) == 1
    assert result.coverage.duplicate_sample_count == 1
    assert any(
        sample.sample_status == SAMPLE_DUPLICATE for sample in result.samples
    )


def test_b0_staying_above_threshold_is_one_crossing():
    result = evaluate_b0(_capture([29.0, 31.0, 31.0, 31.0]), _b0())
    assert len(result.criterion_crossings()) == 1


def test_b0_result_is_diagnostic_not_physical_authority():
    result = evaluate_b0(_capture([29.0, 31.0]), _b0())
    assert result.parameter_status == STATUS_SYNTHETIC
    assert any(
        "not an actuator command" in item for item in result.limitations
    )


def test_b0_wrong_unit_and_invalid_threshold_are_rejected():
    with pytest.raises(Exception):
        evaluate_b0(_capture([30.0]), _b0(representation=_representation(unit="degF")))
    with pytest.raises(Exception):
        _b0(threshold=float("nan"))
    with pytest.raises(Exception):
        _b0(threshold=True)
    with pytest.raises(Exception):
        _b0(max_gap=0.0)


def test_b0_time_domain_mismatch_is_refused():
    result = evaluate_b0(_capture([30.0]), _b0(time_domain="EVENT_UTC"))
    assert result.refusal_reason == REFUSAL_TIME_DOMAIN


def test_b0_missing_or_reversed_time_is_refused():
    rows = [
        dataclasses.replace(_row(0, 29.0), device_ms=None),
        _row(1, 31.0, time_ms=1000),
    ]
    capture = _capture([], rows=rows)
    result = evaluate_b0(capture, _b0())
    assert result.evaluability == EVALUABILITY_REFUSED
    rows = [
        _row(0, 29.0, time_ms=2000),
        _row(1, 31.0, time_ms=1000),
    ]
    capture = _capture([], rows=rows)
    result = evaluate_b0(capture, _b0())
    assert result.evaluability == EVALUABILITY_REFUSED


def test_b0_pre_observation_crossing_is_left_censored():
    result = evaluate_b0(_capture([31.0, 31.0]), _b0())
    crossing = result.criterion_crossings()[0]
    assert crossing.time_certainty == CERTAINTY_BEFORE
    assert crossing.crossing_interval_start_s is None


# ---------------------------------------------------------------------------
# B1 — hysteresis, initial state, freshness, persistence
# ---------------------------------------------------------------------------


def test_b1_on_at_exact_upper_boundary():
    result = evaluate_b1(_capture([29.0, 30.0]), _b1(upper=30.0, lower=28.0))
    assert [item.event_type for item in result.transitions] == [TRANSITION_ON]
    assert result.transitions[0].time_s == 1.0
    assert result.transitions[0].time_certainty == CERTAINTY_EXACT


def test_b1_off_at_exact_lower_boundary_when_previously_on():
    result = evaluate_b1(
        _capture([30.5, 28.0]), _b1(upper=30.0, lower=28.0, initial=INITIAL_ON)
    )
    assert [item.event_type for item in result.transitions] == [TRANSITION_OFF]
    assert result.transitions[0].time_s == 1.0


def test_b1_holds_inside_the_hysteresis_band():
    result = evaluate_b1(
        _capture([29.0, 29.5, 29.0]), _b1(upper=30.0, lower=28.0)
    )
    assert result.transitions == ()
    assert all(sample.decision == "OFF" for sample in result.samples)


def test_b1_initial_state_unavailable_is_not_invented_off():
    result = evaluate_b1(
        _capture([29.0, 30.0]),
        _b1(upper=30.0, lower=28.0, initial=INITIAL_UNAVAILABLE),
    )
    assert result.samples[0].new_state is None
    assert result.samples[0].decision == "UNKNOWN"
    assert [item.event_type for item in result.transitions] == [TRANSITION_ON]
    assert result.transitions[0].prior_state is None


def test_b1_initial_state_evidence_is_required():
    with pytest.raises(Exception):
        dataclasses.replace(_b1(), initial_state_source="")
    with pytest.raises(Exception):
        _b1(upper=28.0, lower=30.0)


def test_b1_does_not_consume_device_reported_applied_state():
    rows = [
        _row(0, 29.0, applied="ON"),
        _row(1, 30.5, applied="OFF"),
        _row(2, 27.0, applied="ON"),
    ]
    result = evaluate_b1(
        _capture([], rows=rows), _b1(upper=30.0, lower=28.0, initial=INITIAL_OFF)
    )
    assert [item.event_type for item in result.transitions] == [
        TRANSITION_ON,
        TRANSITION_OFF,
    ]
    assert result.transitions[0].prior_state == STATE_OFF
    assert result.transitions[1].new_state == STATE_OFF


def test_b1_stale_thermal_input_is_refused():
    rows = [
        _row(0, 29.0, age_ms=10),
        _row(1, 30.5, age_ms=9000),
    ]
    result = evaluate_b1(
        _capture([], rows=rows),
        _b1(upper=30.0, lower=28.0, quality=ThermalQualityPolicy(max_probe_age_s=5.0)),
    )
    assert result.transitions == ()
    assert any(
        sample.sample_status == SAMPLE_STALE for sample in result.samples
    )


def test_b1_cross_boot_is_refused_and_does_not_carry_state():
    rows = [
        _row(0, 30.5, boot_id="boot-1"),
        _row(1, 29.0, boot_id="boot-2"),
    ]
    result = evaluate_b1(_capture([], rows=rows), _b1())
    assert result.evaluability == EVALUABILITY_REFUSED
    assert result.refusal_reason == REFUSAL_MIXED_BOOT


def test_b1_duplicate_delivery_does_not_reevaluate_state():
    rows = [
        _row(0, 30.5),
        _row(0, 27.0, dedup_key=("boot-1", "1")),
        _row(1, 29.0),
    ]
    result = evaluate_b1(
        _capture([], rows=rows), _b1(upper=30.0, lower=28.0, initial=INITIAL_OFF)
    )
    assert [item.event_type for item in result.transitions] == [TRANSITION_ON]
    assert any(
        sample.sample_status == SAMPLE_DUPLICATE for sample in result.samples
    )


def test_b1_persistence_counts_elapsed_seconds_not_samples():
    rows = [
        _row(0, 27.0, time_ms=0),
        _row(1, 27.0, time_ms=1000),
        _row(2, 27.0, time_ms=2000),
        _row(3, 27.0, time_ms=3000),
    ]
    persistence = PersistenceCandidateConfig(
        required_s=3.0, source="synthetic exploratory persistence"
    )
    result = evaluate_b1(
        _capture([], rows=rows),
        _b1(upper=26.0, lower=24.0),
        persistence=persistence,
    )
    assert result.baseline == B1_PERSISTENCE_CANDIDATE
    assert [item.event_type for item in result.transitions] == [TRANSITION_ON]
    assert result.transitions[0].time_s == 3.0


def test_b1_persistence_exact_boundary_and_gap_reset():
    persistence = PersistenceCandidateConfig(
        required_s=3.0, source="synthetic exploratory persistence"
    )
    exact = evaluate_b1(
        _capture(
            [],
            rows=[
                _row(0, 27.0, time_ms=0),
                _row(1, 27.0, time_ms=3000),
            ],
        ),
        _b1(upper=26.0, lower=24.0, max_gap=5.0),
        persistence=persistence,
    )
    assert exact.transitions[0].time_s == 3.0
    gapped = evaluate_b1(
        _capture(
            [],
            rows=[
                _row(0, 27.0, time_ms=0),
                _row(1, 27.0, time_ms=10000),
            ],
        ),
        _b1(upper=26.0, lower=24.0, max_gap=5.0),
        persistence=persistence,
    )
    assert gapped.transitions == ()
    assert gapped.persistence["reset_events"] >= 1


def test_b1_persistence_resets_on_invalid_sample():
    rows = [
        _row(0, 27.0, time_ms=0),
        _row(1, 27.0, time_ms=1000, thermal_quality="INVALID"),
        _row(2, 27.0, time_ms=2000),
        _row(3, 27.0, time_ms=3000),
    ]
    persistence = PersistenceCandidateConfig(
        required_s=3.0, source="synthetic exploratory persistence"
    )
    result = evaluate_b1(
        _capture([], rows=rows),
        _b1(upper=26.0, lower=24.0),
        persistence=persistence,
    )
    assert result.transitions == ()
    assert result.persistence["reset_events"] >= 1


def test_persistence_candidate_cannot_be_labelled_controller_a():
    with pytest.raises(Exception):
        PersistenceCandidateConfig(
            required_s=3.0,
            source="synthetic",
            status="FROZEN_CONTROLLER_A_DWELL",
        )


def test_d_parity_on_pure_hysteresis_comparator():
    sys.path.insert(0, str(REPO_ROOT / "control" / "src"))
    try:
        from coldguard_control.config import PolicyConfig
        from coldguard_control.policy import _hysteresis
        from coldguard_control.types import CoolingState
    finally:
        sys.path.pop(0)
    config = PolicyConfig(
        policy_version="d-synthetic-parity-v1",
        representative_source="TMAX",
        upper_on_c=30.0,
        lower_off_c=28.0,
        thermal_max_age_s=5.0,
        command_max_future_skew_s=60.0,
        broker_offline_grace_s=10.0,
        backend_state_max_age_s=10.0,
        safe_local_exit_min_stable_s=5.0,
        predictive_enabled=False,
    )
    values = [29.0, 30.0, 29.0, 28.0, 27.0, 31.0]
    result = evaluate_b1(
        _capture(values), _b1(upper=30.0, lower=28.0, initial=INITIAL_OFF)
    )
    state = STATE_OFF
    expected_transitions = []
    for index, value in enumerate(values):
        intent, _reason, _detail = _hysteresis(
            value,
            CoolingState.ON if state == STATE_ON else CoolingState.OFF,
            config,
        )
        if intent.value == "ON" and state != STATE_ON:
            state = STATE_ON
            expected_transitions.append((TRANSITION_ON, float(index)))
        elif intent.value == "OFF" and state == STATE_ON:
            state = STATE_OFF
            expected_transitions.append((TRANSITION_OFF, float(index)))
    observed = [
        (item.event_type, item.time_s) for item in result.transitions
    ]
    assert observed == expected_transitions


def test_predictive_persistence_is_not_reused_as_reactive_dwell():
    import coldguard_ml.baselines as baselines_module

    source = Path(baselines_module.__file__).read_text(encoding="utf-8")
    assert "persistence_required_s" not in source
    with pytest.raises(Exception):
        HysteresisConfig(
            **{
                **{
                    field.name: getattr(_b1(), field.name)
                    for field in dataclasses.fields(HysteresisConfig)
                },
                "initial_state_source": "",
            }
        )


def test_b1_limitations_do_not_claim_full_controller_parity():
    result = evaluate_b1(_capture([29.0]), _b1())
    assert result.baseline == B1_HYSTERESIS
    assert any("does not implement fault" in item for item in result.limitations)
    assert not any("SAFE_LOCAL" in item.event_type for item in result.transitions)


def test_representative_value_uses_role_qualified_slots():
    capture = _capture([30.0])
    value = representative_value(capture, capture.rows[0], _representation())
    assert value == pytest.approx(30.0)
    assert "t2" not in _representation().slots


# ---------------------------------------------------------------------------
# CLI and real-data integration
# ---------------------------------------------------------------------------

import csv
import hashlib
import json
import subprocess
import tempfile

W09_CLI = Path(
    os.environ.get(
        "W09_CLI", ML_ROOT / "scripts" / "baseline-evaluation-W09.py"
    )
)
W09_SENSITIVITY = Path(
    os.environ.get(
        "W09_SENSITIVITY",
        ML_ROOT / "baselines" / "sensitivity-example-W09.json",
    )
)
W08_MANIFEST = ML_ROOT / "reports" / "W08" / "gate-b-manifest-W08.json"


def _run_cli(arguments):
    return subprocess.run(
        [sys.executable, str(W09_CLI), *arguments],
        cwd=ML_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _base_args(output: Path, *, sensitivity: bool = True):
    args = [
        "--source",
        str(REAL_A_EXPORT),
        "--a-run-index",
        str(REAL_A_INDEX),
        "--a-w08-manifest",
        str(W08_MANIFEST),
        "--out",
        str(output),
        "--repository-revision",
        "w09-test",
    ]
    if sensitivity:
        args.extend(["--sensitivity", str(W09_SENSITIVITY)])
    return args


def test_w09_cli_help():
    result = _run_cli(["--help"])
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()
    assert "W09" in result.stdout


def test_w09_cli_missing_argument_is_exit_1():
    result = _run_cli([])
    assert result.returncode == 1
    assert "INVALID CONFIGURATION" in result.stderr


def test_w09_cli_refused_source_is_exit_2(tmp_path):
    result = _run_cli(
        [
            "--source",
            str(ML_ROOT / "pyproject.toml"),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert result.returncode == 2
    assert "SOURCE REFUSED" in result.stderr


def test_w09_cli_malformed_w08_manifest_is_exit_1(tmp_path):
    bad = tmp_path / "bad-w08.json"
    bad.write_text("{not-json", encoding="utf-8")
    result = _run_cli(
        [
            "--source",
            str(REAL_A_EXPORT),
            "--a-run-index",
            str(REAL_A_INDEX),
            "--a-w08-manifest",
            str(bad),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert result.returncode == 1
    assert "INVALID CONFIGURATION" in result.stderr


def test_w09_cli_frozen_parameters_cannot_reference_invalid_real_run(tmp_path):
    payload = json.loads(W09_SENSITIVITY.read_text(encoding="utf-8"))
    payload["parameter_status"] = "FROZEN"
    payload["freeze_evidence"] = "fabricated owner decision"
    payload["run_id"] = "CG-S1-INVALID"
    payload["b0"]["threshold_status"] = "FROZEN"
    payload["b1"]["freeze_status"] = "FROZEN"
    path = tmp_path / "frozen.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_cli(
        [
            "--source",
            str(REAL_A_EXPORT),
            "--a-run-index",
            str(REAL_A_INDEX),
            "--a-w08-manifest",
            str(W08_MANIFEST),
            "--parameters",
            str(path),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert result.returncode == 1
    assert "INVALID CONFIGURATION" in result.stderr


def test_w09_cli_real_diagnostic_artifacts_are_consistent(tmp_path):
    output = tmp_path / "w09"
    result = _run_cli(_base_args(output))
    assert result.returncode == 0, result.stderr
    for name in (
        "baseline-report.md",
        "baseline-events-W09.csv",
        "false-warning-summary-W09.csv",
        "baseline-comparison-W09.svg",
        "baseline-manifest-W09.json",
    ):
        assert (output / name).is_file()
    manifest = json.loads(
        (output / "baseline-manifest-W09.json").read_text(encoding="utf-8")
    )
    assert manifest["authoritative_result"] == "PARAMETERS_NOT_FROZEN"
    assert manifest["locked_test_access"] == "NONE"
    assert manifest["w08"]["physical_gate"] == "RED"
    assert manifest["w08"]["a_ledger_verdict"] == "INVALID"
    assert manifest["synthetic_controls"]["status"] == "SYNTHETIC_CONTROL_ONLY"
    for name, digest in manifest["artifact_sha256"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    report = (output / "baseline-report.md").read_text(encoding="utf-8")
    assert "PARAMETERS_NOT_FROZEN" in report
    assert "real S1 false-warning rate = NOT_ESTIMABLE" in report
    assert "NOT physical baseline evidence" in (
        output / "baseline-comparison-W09.svg"
    ).read_text(encoding="utf-8")
    rows = list(
        csv.DictReader(
            (output / "false-warning-summary-W09.csv").open(
                encoding="utf-8", newline=""
            )
        )
    )
    assert any(row["label"] == "AUTHORITATIVE" for row in rows)
    assert any(
        row["label"] == "SOFTWARE_ONLY_SENSITIVITY_NOT_EVIDENTIARY"
        for row in rows
    )


def test_w09_cli_replay_is_deterministic(tmp_path):
    output = tmp_path / "w09"
    arguments = _base_args(output)
    first = _run_cli(arguments)
    assert first.returncode == 0, first.stderr
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in output.iterdir()
    }
    second = _run_cli(arguments)
    assert second.returncode == 0, second.stderr
    assert hashes == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in output.iterdir()
    }


def test_w09_cli_synthetic_control_label_never_physical(tmp_path):
    result = _run_cli(
        [
            "--source",
            str(REAL_A_EXPORT),
            "--a-run-index",
            str(REAL_A_INDEX),
            "--a-w08-manifest",
            str(W08_MANIFEST),
            "--parameters",
            str(W09_SENSITIVITY),
            "--synthetic-control",
            "--out",
            str(tmp_path / "synthetic"),
            "--repository-revision",
            "w09-synthetic-test",
        ]
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads(
        (tmp_path / "synthetic" / "baseline-manifest-W09.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["authoritative_result"] == "SYNTHETIC_ILLUSTRATIVE"
    assert all(
        item["replay"]["parameter_status"] == "SYNTHETIC_ILLUSTRATIVE"
        for item in manifest["baselines"]
    )
    assert all(
        item["s1"]["synthetic_control"] is True
        for item in manifest["baselines"]
    )
    assert manifest["w08"]["physical_gate"] == "RED"
    assert manifest["w08"]["s1_eligibility"] == "BLOCKED"


def test_w09_cli_refuses_synthetic_parameters_without_flag(tmp_path):
    result = _run_cli(
        [
            "--source",
            str(REAL_A_EXPORT),
            "--a-run-index",
            str(REAL_A_INDEX),
            "--a-w08-manifest",
            str(W08_MANIFEST),
            "--parameters",
            str(W09_SENSITIVITY),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert result.returncode == 1
    assert "INVALID CONFIGURATION" in result.stderr

