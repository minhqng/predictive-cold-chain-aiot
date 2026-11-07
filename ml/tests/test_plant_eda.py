"""B-W07-01 … B-W07-04 adversarial, statistical and integration tests.

Software fixtures are explicitly synthetic. The real A W09 export and A's W07
reference bundle are consumed read-only. No test drives hardware, trains a
model or opens a locked test.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

import pytest

from coldguard_ml import load_capture
from coldguard_ml.intake import (
    AValidityEvidence,
    Capture,
    NormalizedRow,
    ProbeReading,
    RunIdentity,
    SensorRole,
    SourceIdentity,
    TimeSemantics,
    chamber_air_mean,
)
from coldguard_ml.plant_eda import (
    APPLIED_COOLING,
    APPLIED_OFF,
    APPLIED_UNDETERMINED,
    CONFOUNDER_NOT_CARRIED,
    CONFOUNDER_OBSERVED,
    CONFOUNDER_NOT_COMPARABLE,
    CONFOUNDER_UNQUALIFIED,
    CV_DEFINED,
    CV_UNDEFINED_MEAN,
    CV_UNDEFINED_N_LT_2,
    CV_UNDEFINED_NON_POSITIVE,
    CV_UNDEFINED_SCALE,
    PHASE_COOLING_STEP,
    PHASE_PASSIVE_WARMUP,
    PHASE_POST_ACTION_RECOVERY,
    PHASE_UNDETERMINED,
    REPEATABILITY_ESTABLISHED,
    REPEATABILITY_NOT_ESTABLISHED,
    PlantEDAConfig,
    PlantEDAError,
    RunRecord,
    analyze_capture_eda,
    analyze_phase,
    analyze_repeatability,
    analyze_synthetic_control,
    build_manifest,
    build_representations,
    classify_applied_state,
    cross_check_a_references,
    detect_electrical_anomalies,
    qualify_run,
    render_pairing_markdown,
    render_plant_svg,
    render_report,
    repeatability_csv,
    representation_value,
    segment_phases,
    summarize_metric,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "ml"
REAL_A_EXPORT = REPO_ROOT / "evidence/A/W09/exports/CG-S1-H8C-600S.json"
REAL_A_INDEX = REPO_ROOT / "evidence/A/W09/s1-run-index.json"
A_W07_DIR = REPO_ROOT / "evidence/A/W07"
CLI = ML_ROOT / "scripts" / "plant-eda-W07.py"

SENSORS = (
    SensorRole(
        slot="t1",
        rom="ROM-T1",
        rom_source="TEST",
        rom_readback_verified=True,
        physical_position="CHAMBER_CENTER",
        position_source="TEST",
        in_chamber_air_aggregate=True,
        exclusion_reason=None,
        raw_roles=("UNASSIGNED",),
        role_conflict=None,
    ),
    SensorRole(
        slot="t2",
        rom="ROM-T2",
        rom_source="TEST",
        rom_readback_verified=True,
        physical_position="TEC_HOT_SIDE",
        position_source="TEST",
        in_chamber_air_aggregate=False,
        exclusion_reason="TEC_HOT_SIDE is a heatsink, not chamber air",
        raw_roles=("HOT_SIDE",),
        role_conflict=None,
    ),
    SensorRole(
        slot="t3",
        rom="ROM-T3",
        rom_source="TEST",
        rom_readback_verified=True,
        physical_position="CHAMBER_BOTTOM",
        position_source="TEST",
        in_chamber_air_aggregate=True,
        exclusion_reason=None,
        raw_roles=("UNASSIGNED",),
        role_conflict=None,
    ),
    SensorRole(
        slot="t4",
        rom="ROM-T4",
        rom_source="TEST",
        rom_readback_verified=True,
        physical_position="CHAMBER_NEAR_DOOR",
        position_source="TEST",
        in_chamber_air_aggregate=True,
        exclusion_reason=None,
        raw_roles=("UNASSIGNED",),
        role_conflict=None,
    ),
)


def _row(
    seq,
    device_ms,
    *,
    t1=20.0,
    t2=21.0,
    t3=20.1,
    t4=20.2,
    applied="OFF",
    duty=0,
    requested=None,
    door="CLOSED",
    overall="VALID",
    power=0.0,
    current=0.0,
    voltage=11.9,
    energy=0.0,
    run_id="run-1",
    boot="boot-1",
    with_t4=True,
    t4_status="OK",
    thermal="VALID",
    electrical="UNKNOWN",
    environment="UNKNOWN",
    doorq="UNKNOWN",
):
    probes = [
        ProbeReading(slot="t1", value_c=t1, status="OK", role="UNASSIGNED", age_ms=40,
                     rom="ROM-T1", physical_position="CHAMBER_CENTER"),
        ProbeReading(slot="t2", value_c=t2, status="OK", role="HOT_SIDE", age_ms=40,
                     rom="ROM-T2", physical_position="TEC_HOT_SIDE"),
        ProbeReading(slot="t3", value_c=t3, status="OK", role="UNASSIGNED", age_ms=40,
                     rom="ROM-T3", physical_position="CHAMBER_BOTTOM"),
    ]
    if with_t4:
        probes.append(
            ProbeReading(slot="t4", value_c=t4, status=t4_status, role="UNASSIGNED",
                         age_ms=40, rom="ROM-T4", physical_position="CHAMBER_NEAR_DOOR")
        )
    quality = (
        ("producer", "VALID"),
        ("thermal", thermal),
        ("environment", environment),
        ("electrical", electrical),
        ("door", doorq),
        ("sequence", "VALID"),
        ("provenance", "VALID"),
        ("overall", overall),
    )
    return NormalizedRow(
        seq=seq,
        boot_id=boot,
        run_id=run_id,
        device_id="dev-1",
        hardware_config_id="CG-HW-TEST",
        firmware_version="test-fw",
        device_ms=device_ms,
        event_time_utc=None,
        host_capture_time_utc=None,
        probes=tuple(probes),
        t_air_c=22.0,
        rh_pct=50.0,
        pressure_hpa=1013.0,
        door_state=door,
        door_polarity="NORMAL",
        cooling_voltage_v=voltage,
        cooling_current_a=current,
        cooling_power_w=power,
        cooling_energy_counter_wh=energy,
        electrical_measured_fields=("voltage_v", "current_a", "power_w", "energy_wh"),
        applied_cooling=applied,
        applied_duty=None if duty is None else duty / 1000.0,
        applied_duty_permille=duty,
        requested_duty_permille=duty if requested is None else requested,
        readback_duty_permille=duty,
        device_state="COOLING" if applied == "ON" else "OFF",
        experiment_phase=None,
        quality=quality,
        overall_quality=overall,
        producer_quality="VALID",
        usable_for=("thermal",),
        invalidation_reasons=(),
        source_line_index=seq + 1,
        dedup_key=("test", boot, str(seq)),
    )


def _capture(rows, *, a_valid=True, run_id="run-1", boot="boot-1", device="dev-1"):
    source = SourceIdentity(
        path="synthetic-capture.json",
        sha256=hashlib.sha256(b"synthetic-capture").hexdigest(),
        format="test-synthetic",
        schema_namespace="test-synthetic/v1",
        provenance="PHYSICAL",
        is_physical_measurement=True,
    )
    run = RunIdentity(
        run_id=run_id,
        run_id_status="SOURCE_CARRIED_SINGLE",
        run_ids=(run_id,),
        boot_id=boot,
        boot_id_status="SOURCE_CARRIED_SINGLE",
        device_id=device,
        device_id_status="CARRIED",
        hardware_config_id="CG-HW-TEST",
        hardware_config_status="VERIFIED",
        firmware_version="test-fw",
        firmware_version_status="CARRIED",
        calibration_id="CG-CAL-TEST",
        calibration_status="VERIFIED",
        scenario_id="S1",
        scenario_status="CERTIFIED",
        controller_id=None,
        controller_status="NOT_CARRIED",
        device_run_label="test",
    )
    validity = AValidityEvidence(
        source="test",
        is_valid=a_valid,
        status="VALID" if a_valid else "INVALID",
        reasons=(),
        rows_usable_per_scenario=(("S1", len(rows)),),
        required_domains=(),
        reason_counts=(),
        rows_total=len(rows),
        usable_fraction=1.0 if a_valid else 0.0,
        hardware_config_verified=True,
        calibration_verified=True,
        clock_sync_verified=False,
        valid_scenarios=("S1",) if a_valid else (),
    )
    return Capture(
        source=source,
        run=run,
        time=TimeSemantics(
            domain="BOOT_SCOPED_UPTIME",
            event_time_status="UNAVAILABLE",
            clock_sync="NOT_EVIDENCED",
            boot_scoped=True,
            cross_boot_join_allowed=False,
            absolute_latency_supported=False,
            detail="test",
        ),
        rows=tuple(rows),
        sensors=SENSORS,
        a_validity=validity,
    )


def _real_capture():
    return load_capture(REAL_A_EXPORT, a_run_index=REAL_A_INDEX)


def _real_references():
    references = {}
    for phase, name in (
        ("baseline", "warmup-runs.jsonl"),
        ("cooling", "cooling-step-runs.jsonl"),
        ("recovery", "recovery-runs.jsonl"),
    ):
        lines = [
            line
            for line in (A_W07_DIR / name).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if lines:
            references[phase] = json.loads(lines[0])
    return references


@pytest.fixture(scope="module")
def real_result():
    return analyze_capture_eda(
        _real_capture(),
        a_w07_references=_real_references(),
    )


def _phase_metrics(capture, phase_name, config=None):
    config = config or PlantEDAConfig()
    representations = build_representations(capture)
    phases = segment_phases(capture)
    phase = next(phase for phase in phases if phase.phase == phase_name)
    return analyze_phase(
        capture,
        phase,
        representations[config.representation],
        config=config,
    )


def _record(
    phase,
    value,
    *,
    source="source-1",
    boot="boot-1",
    device="dev-1",
    run_id="run-1",
    scenario="S1",
    hardware="CG-HW-TEST",
    hardware_status="VERIFIED",
    calibration="CG-CAL-TEST",
    calibration_status="VERIFIED",
    scenario_status="CERTIFIED",
    admission="PHYSICALLY_QUALIFIED",
    a_valid=True,
    synthetic=False,
    pair_id=None,
    metric="minutes_to_1c",
    omit_metric=False,
):
    return RunRecord(
        source_path=f"{source}.json",
        source_sha256=source,
        boot_id=boot,
        device_id=device,
        run_id=run_id,
        scenario_id=scenario,
        scenario_status=scenario_status,
        hardware_config_id=hardware,
        hardware_config_status=hardware_status,
        calibration_id=calibration,
        calibration_status=calibration_status,
        firmware_version="test-fw",
        admission_status=admission,
        a_valid=a_valid,
        synthetic=synthetic,
        pair_id=pair_id,
        controller_arm=None,
        phase=phase,
        outcomes=() if omit_metric else ((metric, value),),
        quality=(
            ("thermal", "VALID"),
            ("sequence", "VALID"),
            ("provenance", "VALID"),
        ),
        reason_codes=(),
    )


def _run_cli(arguments, cwd=ML_ROOT):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ML_ROOT / "src")
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
        env=environment,
    )


# ---------------------------------------------------------------------------
# Phase segmentation and measurement
# ---------------------------------------------------------------------------


def test_real_capture_segments_into_three_phases(real_result):
    counts = {phase.phase: phase.rows for phase in real_result.phases}
    assert counts == {
        PHASE_PASSIVE_WARMUP: 226,
        PHASE_COOLING_STEP: 600,
        PHASE_POST_ACTION_RECOVERY: 131,
    }
    assert all(phase.independent_experiment is False for phase in real_result.phases)
    assert all(
        "SAME_BOOT_PHASE_SEGMENT_IS_NOT_AN_INDEPENDENT_RUN" in phase.reason_codes
        for phase in real_result.phases
    )


def test_two_source_run_labels_in_one_boot_do_not_establish_independence(real_result):
    assert real_result.capture.run.run_ids == ("run-00000000", "run-00000001")
    assert real_result.repeatability.independent_physical_sources == 1
    assert real_result.repeatability.qualified_independent_runs == 0


def test_unknown_applied_state_is_undetermined_not_off():
    label_only = classify_applied_state(_row(1, 1000, applied="OFF", duty=None))
    assert label_only.state == APPLIED_UNDETERMINED
    assert "APPLIED_STATE_UNDETERMINED" in label_only.reason_codes
    both_absent = classify_applied_state(_row(1, 1000, applied=None, duty=None))
    assert both_absent.state == APPLIED_UNDETERMINED
    rows = [
        _row(1, 1000, applied="OFF", duty=None),
        _row(2, 2000, applied="ON", duty=None),
    ]
    capture = _capture(rows)
    phases = segment_phases(capture)
    assert [phase.phase for phase in phases] == [PHASE_UNDETERMINED]
    assert phases[0].undetermined_rows == 2
    metric = _phase_metrics(capture, PHASE_UNDETERMINED)
    assert metric.qualification == "NOT_ESTIMABLE"
    assert "APPLIED_STATE_UNDETERMINED" in metric.reason_codes


def test_applied_label_contradiction_is_undetermined():
    state = classify_applied_state(_row(1, 1000, applied="OFF", duty=500))
    assert state.state == APPLIED_UNDETERMINED
    assert "APPLIED_LABEL_CONTRADICTS_DUTY" in state.reason_codes


def test_requested_duty_differs_from_applied_is_flagged():
    state = classify_applied_state(
        _row(1, 1000, applied="ON", duty=999, requested=1000)
    )
    assert state.state == APPLIED_COOLING
    assert "REQUESTED_DUTY_DIFFERS_FROM_APPLIED" in state.reason_codes


def test_missing_representation_term_prevents_substitution():
    rows = [
        _row(1, 1000, t4=20.2),
        _row(2, 2000, with_t4=False),
        _row(3, 3000, t4=20.4),
    ]
    capture = _capture(rows)
    representations = build_representations(capture)
    air = representations["tmean_airroles_v0"]
    values = [representation_value(capture, row, air) for row in rows]
    assert values[0].value_c == pytest.approx((20.0 + 20.1 + 20.2) / 3)
    assert values[1].value_c is None
    assert "REPRESENTATION_TERM_MISSING" in values[1].reason_codes
    assert values[2].value_c is not None
    metric = _phase_metrics(capture, PHASE_PASSIVE_WARMUP)
    assert metric.rows == 3
    assert metric.usable_rows == 2
    assert metric.skipped_rows == 1


def test_invalid_probe_status_prevents_representation_value():
    rows = [
        _row(1, 1000),
        _row(2, 2000, t4_status="INVALID"),
        _row(3, 3000),
    ]
    capture = _capture(rows)
    representation = build_representations(capture)["tmean_airroles_v0"]
    values = [representation_value(capture, row, representation) for row in rows]
    assert values[1].value_c is None
    assert values[1].quality == "INVALID"
    assert "REPRESENTATION_TERM_INVALID" in values[1].reason_codes
    metric = _phase_metrics(capture, PHASE_PASSIVE_WARMUP)
    assert metric.usable_rows == 2
    assert metric.quality_invalid_rows == 1


def test_phase_segments_preserve_source_boot_and_device_provenance(real_result):
    phase = real_result.phases[0]
    assert phase.source_path == real_result.capture.source.path
    assert phase.source_sha256 == real_result.capture.source.sha256
    assert phase.boot_id == real_result.capture.run.boot_id
    assert phase.device_id == real_result.capture.run.device_id
    payload = phase.to_dict()
    assert payload["source_sha256"] == phase.source_sha256
    assert payload["boot_id"] == phase.boot_id


def test_t2_hot_side_never_enters_chamber_air_representation():
    capture = _capture([_row(1, 1000)])
    representations = build_representations(capture)
    air = representations["tmean_airroles_v0"]
    assert "t2" not in air.slots
    assert air.includes_hot_side is False
    assert air.kind == "CHAMBER_AIR"
    chamber3 = representations["tmean_chamber3_v0"]
    assert "t2" in chamber3.slots
    assert chamber3.includes_hot_side is True
    assert chamber3.kind == "CANONICAL_LITERAL_NON_AIR"
    row = capture.rows[0]
    assert air.slots == ("t1", "t3", "t4")
    assert representation_value(capture, row, air).value_c == pytest.approx(
        chamber_air_mean(capture, row)
    )


def test_irregular_sampling_uses_actual_times_for_energy_and_slope():
    rows = [
        _row(1, 0, t1=20.0, t3=20.0, t4=20.0, power=1.0),
        _row(2, 10_000, t1=20.1, t3=20.1, t4=20.1, power=2.0),
        _row(3, 40_000, t1=20.4, t3=20.4, t4=20.4, power=3.0),
    ]
    metric = _phase_metrics(_capture(rows), PHASE_PASSIVE_WARMUP)
    assert metric.sampled_energy_wh == pytest.approx((1.0 * 10 + 2.0 * 30) / 3600, abs=1e-6)
    assert metric.whole_phase_slope_c_per_min == pytest.approx(0.6)
    assert metric.duration_min == pytest.approx(40 / 60)


def test_true_zero_and_absent_electrical_measurement_are_distinct():
    zero_metric = _phase_metrics(
        _capture([_row(1, 1000, power=0.0), _row(2, 2000, power=0.0)]),
        PHASE_PASSIVE_WARMUP,
    )
    absent_metric = _phase_metrics(
        _capture([_row(1, 1000, power=None, energy=None), _row(2, 2000, power=None, energy=None)]),
        PHASE_PASSIVE_WARMUP,
    )
    assert zero_metric.mean_power_w == 0.0
    assert absent_metric.mean_power_w is None
    assert zero_metric.counter_delta_wh is not None
    assert absent_metric.counter_delta_wh is None


def test_whole_phase_and_trailing_slopes_are_distinct_diagnostics(real_result):
    cooling = real_result.metric_for(PHASE_COOLING_STEP)
    assert cooling is not None
    assert cooling.whole_phase_slope_c_per_min == pytest.approx(-0.854771)
    assert cooling.trailing_slope_c_per_min == pytest.approx(-0.070104)
    assert cooling.trailing_differs_from_whole_phase is True
    assert "whole_phase_least_squares" in cooling.whole_phase_slope_definition
    assert "120samples" in cooling.trailing_slope_definition


def test_peak_direction_and_temperature_change_times(real_result):
    cooling = real_result.metric_for(PHASE_COOLING_STEP)
    assert cooling is not None
    assert cooling.excursion_direction == "COOLING"
    assert cooling.min_c == pytest.approx(21.312667, abs=1e-6)
    assert cooling.max_c == pytest.approx(30.041667, abs=1e-6)
    assert dict(cooling.outcomes)["minutes_to_1c"] == pytest.approx(0.85)
    assert dict(cooling.outcomes)["minutes_to_2c"] == pytest.approx(1.25)


def test_recovery_is_censored_and_not_called_complete(real_result):
    recovery = real_result.metric_for(PHASE_POST_ACTION_RECOVERY)
    assert recovery is not None
    assert recovery.censoring == "CENSORED_AT_CAPTURE_END"
    assert "CENSORED_AT_CAPTURE_END" in recovery.reason_codes
    assert recovery.end_c == pytest.approx(26.645667, abs=1e-6)


def test_spread_uses_chamber_probes_only(real_result):
    warmup = real_result.metric_for(PHASE_PASSIVE_WARMUP)
    cooling = real_result.metric_for(PHASE_COOLING_STEP)
    assert warmup is not None and cooling is not None
    assert warmup.initial_spread_c == pytest.approx(0.374, abs=1e-6)
    first_row_spread = max(
        reading.value_c for reading in real_result.capture.rows[0].probes
        if reading.slot in {"t1", "t3", "t4"}
    ) - min(
        reading.value_c for reading in real_result.capture.rows[0].probes
        if reading.slot in {"t1", "t3", "t4"}
    )
    assert warmup.initial_spread_c == pytest.approx(first_row_spread, abs=1e-6)
    assert "t2" not in real_result.representations["tmean_airroles_v0"].slots


def test_electrical_values_remain_unqualified(real_result):
    cooling = real_result.metric_for(PHASE_COOLING_STEP)
    assert cooling is not None
    assert cooling.electrical_qualification == "UNQUALIFIED"
    assert cooling.electrical_unqualified_rows == 600


def test_off_state_power_anomaly_remains_visible(real_result):
    assert len(real_result.anomalies) == 1
    anomaly = real_result.anomalies[0]
    assert anomaly.device_ms == 826894
    assert anomaly.applied_state == APPLIED_OFF
    assert anomaly.power_w == pytest.approx(84.2)
    assert anomaly.current_a == pytest.approx(7.15)
    assert "COMPETING" not in anomaly.classification
    assert "PZEM" in anomaly.competing_explanation
    assert "no independent conclusion" in anomaly.resolution


def test_cross_check_diagnoses_definitional_differences(real_result):
    references = {
        "cooling": {
            "representation": "tmean_chamber3_v0",
            "delta_c": -2.5627,
        }
    }
    rows = cross_check_a_references(
        real_result.metrics,
        references,
        primary_definition="tmean_airroles_v0",
    )
    assert any(
        row.field == "representation" and row.status == "NOT_COMPARABLE"
        for row in rows
    )
    delta = next(row for row in rows if row.field == "delta_c")
    assert delta.status == "DIFFERS"
    assert "phase boundary, representation, time base and estimator" in delta.detail


def test_initial_state_is_measured_before_the_cooling_action(real_result):
    warmup = real_result.metric_for(PHASE_PASSIVE_WARMUP)
    cooling = real_result.metric_for(PHASE_COOLING_STEP)
    assert warmup is not None and cooling is not None
    warmup_phase = real_result.phases[0]
    cooling_phase = real_result.phases[1]
    assert warmup_phase.start_s is not None and cooling_phase.start_s is not None
    assert warmup_phase.start_s < cooling_phase.start_s
    first_cooling_row = real_result.capture.rows[cooling_phase.start_row_index]
    assert classify_applied_state(first_cooling_row).state == APPLIED_COOLING
    first_row_value = representation_value(
        real_result.capture,
        real_result.capture.rows[0],
        real_result.representations["tmean_airroles_v0"],
    ).value_c
    assert warmup.start_c == pytest.approx(first_row_value, abs=1e-6)


def test_report_shows_ambient_duty_coverage_and_unresolved_dependencies(real_result):
    report = render_report(
        real_result,
        code_sha256="0" * 64,
        repository_revision="test",
        generation_command="test",
    )
    for token in (
        "ambient_first_c",
        "applied_duty_min_permille",
        "cadence_median_s",
        "initial_probes_c",
        "A-W07-01 remains PARTIAL",
        "door",
        "calibration identity is absent",
        "device identity is not carried",
        "configuration is declared, not verified",
    ):
        assert token in report


def test_w06_timing_and_identity_diagnostics_are_consumed(real_result):
    timing = real_result.quality["w06_timing"]
    assert timing["order_status"] == "ORDERED_IN_DOMAIN"
    assert timing["order_reason_codes"] == []
    assert timing["event_count"] == 959
    assert timing["duplicate_deliveries"] == 0
    assert timing["contradictory_identity_count"] == 0
    assert timing["missing_identity_events"] == 0
    assert timing["identity_status_counts"] == {"PARTIAL": 959}
    report = render_report(
        real_result,
        code_sha256="0" * 64,
        repository_revision="test",
        generation_command="test",
    )
    assert "W06 timing/identity diagnostics consumed read-only" in report
    assert "ORDERED_IN_DOMAIN" in report


def test_cross_check_matches_a_w07_references(real_result):
    assert real_result.cross_check
    assert {row.status for row in real_result.cross_check} == {"MATCH"}
    assert len(real_result.cross_check) == 33
    cooling_start = next(
        row for row in real_result.cross_check
        if row.phase == PHASE_COOLING_STEP and row.field == "delta_c"
    )
    assert cooling_start.computed_value == pytest.approx(-8.708333, abs=1e-6)


# ---------------------------------------------------------------------------
# Repeatability and statistics
# ---------------------------------------------------------------------------


def test_one_boot_three_phases_are_not_three_independent_runs(real_result):
    assert real_result.repeatability.diagnostic_phase_records == 3
    assert real_result.repeatability.qualified_independent_runs == 0
    assert real_result.repeatability.verdict == REPEATABILITY_NOT_ESTABLISHED
    assert "NO_QUALIFIED_INDEPENDENT_RUNS" in real_result.repeatability.reason_codes


def test_duplicate_source_views_do_not_inflate_n():
    records = [
        _record(PHASE_COOLING_STEP, 1.0, source="same-source"),
        _record(PHASE_COOLING_STEP, 1.0, source="same-source"),
    ]
    summary = analyze_repeatability(records)
    assert summary.independent_physical_sources == 1
    assert summary.qualified_independent_runs == 1
    assert summary.duplicate_views == 1


def test_invalid_physical_capture_is_excluded():
    records = [
        _record(PHASE_COOLING_STEP, 1.0, a_valid=False, admission="EXCLUDED_OR_BLOCKED")
    ]
    summary = analyze_repeatability(records)
    assert summary.qualified_independent_runs == 0
    assert "A_LEDGER_NOT_VALID" in summary.reason_codes


def test_n0_and_n1_statistics_are_undefined_not_zero():
    empty = summarize_metric(
        [],
        phase=PHASE_COOLING_STEP,
        metric="minutes_to_1c",
        n_qualified=0,
        n_diagnostic=0,
        repeatability_status=REPEATABILITY_NOT_ESTABLISHED,
    )
    single = summarize_metric(
        [5.0],
        phase=PHASE_COOLING_STEP,
        metric="minutes_to_1c",
        n_qualified=0,
        n_diagnostic=1,
        repeatability_status=REPEATABILITY_NOT_ESTABLISHED,
    )
    assert empty.mean is None and empty.sample_sd is None and empty.cv_pct is None
    assert single.mean == 5.0
    assert single.sample_sd is None and single.iqr is None and single.cv_pct is None
    assert single.cv_status == CV_UNDEFINED_N_LT_2


def test_n3_synthetic_fixture_yields_correct_mean_sd_iqr_and_cv():
    records = [
        _record(PHASE_COOLING_STEP, value, source=f"synthetic-{index}", synthetic=True)
        for index, value in enumerate((10.0, 12.0, 14.0))
    ]
    summary = analyze_synthetic_control(records)
    row = next(
        row for row in summary.rows
        if row.phase == PHASE_COOLING_STEP and row.metric == "minutes_to_1c"
    )
    assert row.n_qualified == 3
    assert row.mean == pytest.approx(12.0)
    assert row.sample_sd == pytest.approx(2.0)
    assert row.median == pytest.approx(12.0)
    assert row.q1 == pytest.approx(11.0)
    assert row.q3 == pytest.approx(13.0)
    assert row.iqr == pytest.approx(2.0)
    assert row.cv_pct == pytest.approx(100.0 * 2.0 / 12.0)
    assert row.cv_status == CV_DEFINED


def test_cv_is_undefined_for_zero_mean_and_non_ratio_scale():
    zero = summarize_metric(
        [0.0, 0.0, 0.0],
        phase=PHASE_COOLING_STEP,
        metric="minutes_to_1c",
        n_qualified=3,
        n_diagnostic=0,
        repeatability_status=REPEATABILITY_ESTABLISHED,
    )
    interval = summarize_metric(
        [20.0, 21.0, 22.0],
        phase=PHASE_COOLING_STEP,
        metric="start_c",
        n_qualified=3,
        n_diagnostic=0,
        repeatability_status=REPEATABILITY_ESTABLISHED,
    )
    negative = summarize_metric(
        [-1.0, -2.0, -3.0],
        phase=PHASE_COOLING_STEP,
        metric="mean_power_w",
        n_qualified=3,
        n_diagnostic=0,
        repeatability_status=REPEATABILITY_ESTABLISHED,
    )
    assert zero.cv_pct is None and zero.cv_status == CV_UNDEFINED_MEAN
    assert interval.cv_pct is None and interval.cv_status == CV_UNDEFINED_SCALE
    assert negative.cv_pct is None and negative.cv_status == CV_UNDEFINED_NON_POSITIVE


def test_mixed_hardware_and_calibration_groups_are_not_pooled():
    group_a = [
        _record(PHASE_COOLING_STEP, value, source=f"a-{index}", hardware="HW-A")
        for index, value in enumerate((1.0, 2.0, 3.0))
    ]
    group_b = [
        _record(PHASE_COOLING_STEP, value, source=f"b-{index}", hardware="HW-B")
        for index, value in enumerate((10.0, 11.0, 12.0))
    ]
    summary = analyze_repeatability(group_a + group_b)
    rows = [
        row for row in summary.rows
        if row.phase == PHASE_COOLING_STEP and row.metric == "minutes_to_1c"
    ]
    assert len(rows) == 2
    assert {row.group_id for row in rows} == {
        "S1|COOLING_STEP|HW-A|CG-CAL-TEST",
        "S1|COOLING_STEP|HW-B|CG-CAL-TEST",
    }
    means = sorted(row.mean for row in rows)
    assert means == pytest.approx([2.0, 11.0])
    assert 6.5 not in means


def test_paired_treatment_arms_are_not_plant_replicates():
    records = [
        _record(PHASE_COOLING_STEP, 1.0, source="pair-a", pair_id="PAIR-1"),
        _record(PHASE_COOLING_STEP, 2.0, source="pair-b", pair_id="PAIR-1"),
    ]
    summary = analyze_repeatability(records)
    assert summary.qualified_independent_runs == 0
    assert "PAIRED_TREATMENT_ARM_IS_NOT_A_PLANT_REPLICATE" in summary.reason_codes
    rows = [
        row for row in summary.rows
        if row.phase == PHASE_COOLING_STEP and row.metric == "minutes_to_1c"
    ]
    assert rows
    assert all(row.n_qualified == 0 and row.n_diagnostic == 0 for row in rows)
    assert all(row.mean is None and row.sample_sd is None for row in rows)


def test_multiple_sources_with_multiple_phases_count_runs_not_phase_records():
    records = [
        _record(phase, value, source=f"source-{source_index}")
        for source_index in range(2)
        for phase, value in (
            (PHASE_PASSIVE_WARMUP, 1.0),
            (PHASE_COOLING_STEP, 2.0),
            (PHASE_POST_ACTION_RECOVERY, 3.0),
        )
    ]
    summary = analyze_repeatability(records)
    assert summary.independent_physical_sources == 2
    assert summary.qualified_independent_runs == 2
    assert summary.diagnostic_phase_records == 6


def test_qualified_run_count_is_unique_physical_sources_not_phase_records():
    records = [
        _record(phase, value)
        for phase, value in (
            (PHASE_PASSIVE_WARMUP, 1.0),
            (PHASE_COOLING_STEP, 2.0),
            (PHASE_POST_ACTION_RECOVERY, 3.0),
        )
    ]
    summary = analyze_repeatability(records)
    assert summary.independent_physical_sources == 1
    assert summary.qualified_independent_runs == 1
    assert summary.diagnostic_phase_records == 3
    assert dict(summary.qualified_phase_counts) == {
        PHASE_PASSIVE_WARMUP: 1,
        PHASE_COOLING_STEP: 1,
        PHASE_POST_ACTION_RECOVERY: 1,
    }
    assert summary.verdict == REPEATABILITY_NOT_ESTABLISHED


def test_insufficient_qualified_n_never_produces_established_repeatability():
    records = [
        _record(PHASE_COOLING_STEP, 1.0, source=f"run-{index}")
        for index in range(2)
    ]
    summary = analyze_repeatability(records)
    assert summary.verdict == REPEATABILITY_NOT_ESTABLISHED
    assert "MINIMUM_INDEPENDENT_RUNS_NOT_MET" in summary.reason_codes


def test_missing_outcomes_retain_the_qualified_denominator():
    records = [
        _record(PHASE_COOLING_STEP, 1.0, source=f"run-{index}")
        for index in range(2)
    ] + [
        _record(PHASE_COOLING_STEP, None, source="run-missing", omit_metric=True)
    ]
    summary = analyze_repeatability(records)
    row = next(
        row for row in summary.rows
        if row.phase == PHASE_COOLING_STEP and row.metric == "minutes_to_1c"
    )
    assert row.n_qualified == 3
    assert row.n_values == 2
    assert row.missing_undefined == 1


def test_synthetic_controls_never_enter_the_physical_repeatability_report():
    physical = [_record(PHASE_COOLING_STEP, 1.0, source="physical")]
    synthetic = [
        _record(PHASE_COOLING_STEP, 2.0, source=f"syn-{index}", synthetic=True)
        for index in range(3)
    ]
    summary = analyze_repeatability(physical + synthetic)
    assert summary.qualified_independent_runs == 1
    assert summary.verdict == REPEATABILITY_NOT_ESTABLISHED
    assert "SYNTHETIC_CONTROLS_EXCLUDED_FROM_PHYSICAL_REPORT" in summary.reason_codes
    synthetic_only = analyze_repeatability(synthetic)
    assert synthetic_only.qualified_independent_runs == 0
    control = analyze_synthetic_control(synthetic)
    row = next(
        row for row in control.rows
        if row.phase == PHASE_COOLING_STEP and row.metric == "minutes_to_1c"
    )
    assert row.n_qualified == 3
    assert row.repeatability_status == "SYNTHETIC_CONTROL_ONLY"


def test_qualify_run_requires_complete_physical_identity():
    ok, reasons = qualify_run(_record(PHASE_COOLING_STEP, 1.0))
    assert ok is True and reasons == ()
    denied, denied_reasons = qualify_run(
        _record(
            PHASE_COOLING_STEP,
            1.0,
            device=None,
            calibration=None,
            hardware_status="DECLARED_NOT_VERIFIED",
            scenario_status="CANDIDATE_NOT_CERTIFIED",
        )
    )
    assert denied is False
    assert "DEVICE_IDENTITY_MISSING" in denied_reasons
    assert "CALIBRATION_IDENTITY_MISSING" in denied_reasons
    assert "HARDWARE_CONFIG_NOT_VERIFIED" in denied_reasons
    assert "SCENARIO_NOT_CERTIFIED" in denied_reasons


# ---------------------------------------------------------------------------
# Confounding, pairing, artifacts
# ---------------------------------------------------------------------------


def test_confounding_inventory_marks_absent_factors(real_result):
    statuses = {entry.factor: entry.status for entry in real_result.confounders}
    assert statuses["Initial chamber temperature"] == CONFOUNDER_OBSERVED
    assert statuses["Calibration identity"] == CONFOUNDER_NOT_CARRIED
    assert statuses["Ambient temperature and relative humidity"] == CONFOUNDER_UNQUALIFIED
    assert statuses["Cooling-branch electrical qualification"] == CONFOUNDER_UNQUALIFIED
    assert statuses["Run order and session-day effects"] == CONFOUNDER_NOT_COMPARABLE
    assert all(entry.status in {
        CONFOUNDER_OBSERVED,
        CONFOUNDER_UNQUALIFIED,
        "UNKNOWN",
        CONFOUNDER_NOT_CARRIED,
        "CONTRADICTORY",
        CONFOUNDER_NOT_COMPARABLE,
    } for entry in real_result.confounders)


def test_missing_calibration_and_hardware_verification_remain_missing(real_result):
    report = render_report(
        real_result,
        code_sha256="0" * 64,
        repository_revision="test",
        generation_command="test",
    )
    assert "calibration identity is absent" in report
    assert "configuration is declared, not verified" in report
    pairing = render_pairing_markdown()
    assert "calibration VERIFIED" in pairing
    assert "UNAVAILABLE_VARIABLE" in pairing


def test_pairing_forbids_post_intervention_outcomes_and_invented_tolerance():
    pairing = render_pairing_markdown()
    assert "Post-intervention outcomes must never define a pair" in pairing
    assert "end temperature, ΔT, whole-phase slope" in pairing
    assert "No numeric matching tolerance is claimed" in pairing
    assert "candidate pilot-era values only" in pairing
    assert "0.5" in pairing and "0.3" in pairing


def test_pairing_candidates_retain_units_and_sources():
    pairing = render_pairing_markdown()
    for token in ("°C", "°C/min", "W", "Wh", "DEVICE_BOOT_UPTIME", "thermal VALID"):
        assert token in pairing


def test_report_csv_and_manifest_agree(real_result):
    report = render_report(
        real_result,
        code_sha256="1" * 64,
        repository_revision="test-revision",
        generation_command="python scripts/plant-eda-W07.py --test",
    )
    csv_text = repeatability_csv(real_result.repeatability)
    manifest_text = build_manifest(
        real_result,
        code_sha256="1" * 64,
        repository_revision="test-revision",
        generation_command="python scripts/plant-eda-W07.py --test",
        artifact_sha256={"repeatability-summary.csv": "abc"},
    )
    manifest = json.loads(manifest_text)
    assert manifest["repeatability"]["verdict"] == REPEATABILITY_NOT_ESTABLISHED
    assert manifest["repeatability"]["qualified_independent_runs"] == 0
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert rows
    assert all(row["repeatability_status"] == REPEATABILITY_NOT_ESTABLISHED for row in rows)
    assert all(row["n_qualified_independent_runs"] == "0" for row in rows)
    assert "NOT_ESTABLISHED" in report
    assert "REAL AIW | NOT_ESTIMABLE" in report
    assert manifest["scientific_separation"]["PHYSICAL_REPEATABILITY"] == REPEATABILITY_NOT_ESTABLISHED


def test_svg_is_deterministic_and_marks_single_session(real_result):
    first = render_plant_svg(real_result)
    second = render_plant_svg(real_result)
    assert first == second
    assert "one diagnostic session" in first
    assert "not independent-run repeatability" in first
    assert "UNQUALIFIED" in first
    assert "max(" not in first
    assert "<script" not in first


def test_non_air_primary_representation_is_refused():
    with pytest.raises(PlantEDAError) as exc:
        analyze_capture_eda(
            _real_capture(),
            config=PlantEDAConfig(representation="tmean_chamber3_v0"),
        )
    assert exc.value.code == "NON_AIR_REPRESENTATION_CANNOT_BE_PRIMARY"


def test_multi_boot_capture_is_refused_not_silently_aligned():
    rows = [
        _row(1, 1000, boot="boot-1"),
        _row(2, 2000, boot="boot-2"),
    ]
    with pytest.raises(PlantEDAError) as exc:
        analyze_capture_eda(_capture(rows))
    assert exc.value.code == "MULTIPLE_BOOT_SESSIONS_CANNOT_BE_POOLED"


# ---------------------------------------------------------------------------
# CLI behavior
# ---------------------------------------------------------------------------


def test_cli_help():
    result = _run_cli(["--help"])
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()
    assert "plant EDA" in result.stdout


def test_cli_invalid_configuration_is_exit_1():
    result = _run_cli(
        ["--source", str(REAL_A_EXPORT), "--trailing-samples", "1"]
    )
    assert result.returncode == 1
    assert "INVALID CONFIGURATION" in result.stderr


def test_cli_refused_source_is_exit_2():
    result = _run_cli(["--source", str(A_W07_DIR / "README.md")])
    assert result.returncode == 2
    assert "SOURCE REFUSED" in result.stderr


def test_cli_writes_canonical_artifacts_and_replays_deterministically(tmp_path):
    output = tmp_path / "w07"
    pairing = output / "pairing-candidate-variables.md"
    arguments = [
        "--source",
        str(REAL_A_EXPORT),
        "--a-run-index",
        str(REAL_A_INDEX),
        "--a-w07-dir",
        str(A_W07_DIR),
        "--out",
        str(output),
        "--repository-revision",
        "test-revision",
        "--pairing-out",
        str(pairing),
    ]
    first = _run_cli(arguments)
    assert first.returncode == 0, first.stderr
    names = {
        "plant-eda-report.md",
        "repeatability-summary.csv",
        "phase-trajectories-W07.svg",
        "plant-eda-manifest-W07.json",
        "pairing-candidate-variables.md",
    }
    assert {path.name for path in output.iterdir()} == names
    hashes = {
        name: hashlib.sha256((output / name).read_bytes()).hexdigest()
        for name in names
    }
    second = _run_cli(arguments)
    assert second.returncode == 0, second.stderr
    assert hashes == {
        name: hashlib.sha256((output / name).read_bytes()).hexdigest()
        for name in names
    }
    manifest = json.loads((output / "plant-eda-manifest-W07.json").read_text(encoding="utf-8"))
    assert manifest["repository_revision"] == "test-revision"
    assert manifest["artifact_sha256"]["repeatability-summary.csv"] == hashes[
        "repeatability-summary.csv"
    ]
    assert manifest["repeatability"]["verdict"] == REPEATABILITY_NOT_ESTABLISHED
    report = (output / "plant-eda-report.md").read_text(encoding="utf-8")
    assert "Analysis code SHA-256" in report
    assert "Generation command" in report
    assert "PHYSICAL REPEATABILITY | NOT_ESTABLISHED" in report


def test_no_model_training_or_locked_test_access_in_w07_module():
    text = (ML_ROOT / "src" / "coldguard_ml" / "plant_eda.py").read_text(encoding="utf-8")
    lowered = text.lower()
    for token in ("sklearn", "xgboost", "fit(", "train_test_split", "locked_test"):
        assert token not in lowered
