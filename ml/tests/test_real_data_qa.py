"""B-W05-01 … B-W05-04 adversarial and integration tests.

Controlled fixtures are built through the same W04 A-export shape used by the
W04 tests; the real W09 export and the C fixture are consumed read-only.
"""

from __future__ import annotations

import csv
import dataclasses
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from coldguard_ml import (
    QAConfig,
    SourceRefusal,
    analyze_capture,
    analyze_captures,
    analyze_sessions,
    channel_summary_csv,
    compute_interval_statistics,
    load_capture,
    percentile,
    qa_manifest,
    render_physical_state_svg,
    summarize_qa_suite,
)
from coldguard_ml.real_data_qa import _segments

from test_intake_schema import (
    _positive_export,
    _positive_index,
    write_a_export,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "ml"
REAL_A_EXPORT = REPO_ROOT / "evidence/A/W09/exports/CG-S1-H8C-600S.json"
REAL_A_INDEX = REPO_ROOT / "evidence/A/W09/s1-run-index.json"
C_FIXTURE = REPO_ROOT / "backend/fixtures/telemetry_v0.json"
CLI = ML_ROOT / "scripts" / "real-data-qa-v1.py"


def _real_capture():
    return load_capture(REAL_A_EXPORT, a_run_index=REAL_A_INDEX)


def _row_overrides(times_ms, **common):
    rows = []
    for index, device_ms in enumerate(times_ms, start=1):
        row = {"seq": str(index), "device_ms": str(device_ms)}
        row.update(common)
        rows.append(row)
    return rows


def _export(directory: Path, rows, **kwargs):
    directory.mkdir(parents=True, exist_ok=True)
    return write_a_export(directory, rows=rows, **kwargs)


def _run_cli(arguments, cwd=ML_ROOT):
    return subprocess.run(
        [sys.executable, str(CLI), *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _cli_module():
    spec = importlib.util.spec_from_file_location("w05_cli_under_test", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _conflicting_views(tmp_path):
    """Same export bytes; two alternative A validity ledgers."""
    (tmp_path / "export").mkdir(parents=True)
    (tmp_path / "valid").mkdir(parents=True)
    (tmp_path / "invalid").mkdir(parents=True)
    export = _positive_export(tmp_path / "export")
    valid_index = _positive_index(tmp_path / "valid", valid=True)
    invalid_index = _positive_index(tmp_path / "invalid", valid=False)
    valid_view = load_capture(export, a_run_index=valid_index)
    invalid_view = load_capture(export, a_run_index=invalid_index)
    assert valid_view.source.path == invalid_view.source.path
    assert valid_view.source.sha256 == invalid_view.source.sha256
    assert valid_view.run.boot_id == invalid_view.run.boot_id
    return valid_view, invalid_view


def _channel(analysis, name):
    return next(channel for channel in analysis.channels if channel.channel == name)


def _csv_rows(text: str):
    return list(csv.DictReader(io.StringIO(text)))


# ---------------------------------------------------------------------------
# real A evidence integration
# ---------------------------------------------------------------------------


def test_real_a_export_is_analyzed_without_upgrading_w04_verdict():
    capture = _real_capture()
    analysis = analyze_capture(capture)

    assert analysis.statuses.qa_execution_status == "COMPLETED"
    assert analysis.statuses.source_structure_status == "VALID"
    assert analysis.statuses.channel_quality_status == "ATTENTION_REQUIRED"
    assert analysis.statuses.physical_admission_status == "EXCLUDED_OR_BLOCKED"
    assert analysis.statuses.physical_highest_stage == "USABLE_FOR_DIAGNOSTIC_QA"
    assert analysis.statuses.predictive_dataset_readiness == "NOT_READY"

    assert len(analysis.sessions) == 1
    session = analysis.sessions[0]
    assert session.row_count == 957
    assert session.unique_identity_count == 957
    assert session.duplicate_identity_count == 0
    assert session.scientific_usable_rows == 0
    assert session.scientific_sample_coverage == 0.0
    assert session.campaign_completeness == (
        "NOT_ESTIMABLE_ACQUISITION_BOUNDARIES_UNVERIFIED"
    )

    stats = session.interval_stats
    assert stats.time_base_status == "TRUSTED_BOOT_SCOPED_UPTIME"
    assert stats.interval_count == 956
    assert stats.positive_interval_count == 956
    assert stats.zero_interval_count == 0
    assert stats.negative_interval_count == 0
    assert stats.median_dt_s == pytest.approx(1.0)
    assert stats.p95_dt_s == pytest.approx(1.0)
    assert stats.min_positive_dt_s == pytest.approx(0.99)
    assert stats.max_positive_dt_s == pytest.approx(1.0)
    assert stats.nominal_dt_s == pytest.approx(1.0)
    assert stats.nominal_source == "INFERRED_MODAL_OBSERVED_INTERVAL"
    assert stats.nominal_confidence == "HIGH"
    assert stats.long_gap_count == 0
    assert stats.seq_missing_estimate == 0
    assert stats.seq_semantics == "ALL_DELTAS_ONE"
    assert stats.observation_window_s == pytest.approx(955.99)
    assert stats.expected_samples_provisional == 957
    assert stats.captured_frame_completeness == pytest.approx(1.0)
    assert stats.completeness_status == "PROVISIONAL_DIAGNOSTIC"

    assert capture.chamber_air_slots == ("t1", "t3", "t4")
    assert capture.hot_side_slots == ("t2",)
    t2 = _channel(analysis, "t2")
    assert t2.physical_role == "TEC_HOT_SIDE"
    assert t2.present_count == 957

    assert all(
        channel.physical_admission_status == "EXCLUDED_OR_BLOCKED"
        for channel in analysis.channels
    )
    power = _channel(analysis, "cooling_power_w")
    assert power.quality_unknown == 957
    assert "PZEM_POWER_UNQUALIFIED_DIAGNOSTIC_ONLY" in power.reason_codes
    assert power.diagnostic_status == "DIAGNOSTIC_READABLE_UNQUALIFIED"

    door = _channel(analysis, "door_state")
    assert door.present_count == 940
    assert door.unknown_state_count == 17
    assert "DOOR_NO_OPEN_EVENT_IN_CAPTURE" in door.reason_codes

    codes = {anomaly.code for anomaly in analysis.anomalies}
    assert "RUN_ID_UNRESOLVED" in codes
    assert "HOT_SIDE_EXCLUDED_FROM_CHAMBER_AIR" in codes
    assert "SENSOR_ROM_READBACK_UNVERIFIED" in codes
    assert "DOOR_NO_QUALIFYING_OPEN_EVENT" in codes
    assert "W04_ADMISSION_BLOCKED" in codes


def test_real_a_csv_report_and_plot_agree_and_are_deterministic():
    analysis = analyze_capture(_real_capture())
    first_csv = channel_summary_csv([analysis])
    second_csv = channel_summary_csv([analyze_capture(_real_capture())])
    assert first_csv == second_csv

    parsed = _csv_rows(first_csv)
    assert len(parsed) == len(analysis.channels)
    required = {
        "source_id",
        "source_sha256",
        "device_id",
        "boot_id",
        "run_id",
        "run_id_status",
        "channel",
        "physical_role",
        "unit",
        "row_count",
        "present_count",
        "missing_count",
        "missing_fraction",
        "quality_VALID",
        "quality_DEGRADED",
        "quality_INVALID",
        "quality_UNKNOWN",
        "impossible_count",
        "flatline_candidate_count",
        "stale_candidate_count",
        "duplicate_identity_count",
        "diagnostic_status",
        "reason_codes",
        "physical_admission_status",
    }
    assert required <= set(parsed[0])
    by_channel = {row["channel"]: row for row in parsed}
    for channel in analysis.channels:
        row = by_channel[channel.channel]
        assert int(row["present_count"]) == channel.present_count
        assert int(row["missing_count"]) == channel.missing_count
        assert int(row["quality_VALID"]) == channel.quality_valid
        assert int(row["quality_UNKNOWN"]) == channel.quality_unknown
        assert int(row["impossible_count"]) == channel.impossible_count
        assert row["diagnostic_status"] == channel.diagnostic_status
        assert row["physical_admission_status"] == "EXCLUDED_OR_BLOCKED"
    assert int(by_channel["t1"]["flatline_candidate_count"]) == 13
    assert by_channel["t1"]["stale_candidate_count"] == "0"
    assert by_channel["door_state"]["flatline_candidate_count"] == (
        "NOT_APPLICABLE"
    )
    assert by_channel["door_state"]["stale_candidate_count"] == "NOT_APPLICABLE"

    svg = render_physical_state_svg(
        analysis.capture, analysis.admission, analysis.sessions[0]
    )
    assert svg.count("Panel ") == 5
    assert "UNQUALIFIED PZEM VALUES" in svg
    assert "TEC hot-side" in svg
    assert "Gaps are not connected; missing values are not zero" in svg


# ---------------------------------------------------------------------------
# sampling statistics
# ---------------------------------------------------------------------------


def test_perfect_1hz_sequence_has_expected_statistics(tmp_path):
    export = _export(tmp_path, _row_overrides(range(1000, 21000, 1000)))
    analysis = analyze_capture(load_capture(export))
    stats = analysis.sessions[0].interval_stats
    assert stats.median_dt_s == pytest.approx(1.0)
    assert stats.p95_dt_s == pytest.approx(1.0)
    assert stats.min_positive_dt_s == pytest.approx(1.0)
    assert stats.max_positive_dt_s == pytest.approx(1.0)
    assert stats.jitter_p95_abs_s == pytest.approx(0.0)
    assert stats.long_gap_count == 0


def test_irregular_cadence_and_percentile_method_are_documented():
    times = [0.0, 1.0, 2.0, 2.5, 4.0, 5.0]
    seqs = [1, 2, 3, 4, 5, 6]
    linear = compute_interval_statistics(times, seqs, config=QAConfig())
    nearest = compute_interval_statistics(
        times,
        seqs,
        config=QAConfig(percentile_method="nearest_rank"),
    )
    assert linear.p95_dt_s == pytest.approx(1.4)
    assert nearest.p95_dt_s == pytest.approx(1.5)
    assert linear.median_dt_s == pytest.approx(1.0)
    assert percentile([1, 2, 3, 4, 5], 0.95, "linear") == pytest.approx(4.8)
    assert percentile([1, 2, 3, 4, 5], 0.95, "nearest_rank") == 5


def test_long_gap_boundary_is_strictly_above_threshold(tmp_path):
    # intervals: 1.0 (below), 2.0 (equal), 2.001 (above)
    export = _export(
        tmp_path,
        _row_overrides([0, 1000, 2000, 4000, 6001]),
    )
    analysis = analyze_capture(load_capture(export), config=QAConfig(long_gap_ms=2000))
    stats = analysis.sessions[0].interval_stats
    assert stats.long_gap_count == 1
    assert stats.long_gap_total_s == pytest.approx(2.001)


def test_zero_and_negative_intervals_are_counted_not_discarded(tmp_path):
    export = _export(tmp_path, _row_overrides([0, 1000, 1000, 2000]))
    analysis = analyze_capture(load_capture(export))
    stats = analysis.sessions[0].interval_stats
    assert stats.zero_interval_count == 1
    assert stats.positive_interval_count == 2
    assert stats.median_dt_s == pytest.approx(1.0)
    # The honest captured-frame ratio can exceed 1 when timestamps repeat.
    assert stats.captured_frame_completeness is not None
    assert stats.captured_frame_completeness > 1.0

    negative = compute_interval_statistics(
        [0.0, 1.0, 0.5, 1.5],
        [1, 2, 3, 4],
        config=QAConfig(),
    )
    assert negative.negative_interval_count == 1
    assert negative.time_base_status == "TIME_BASE_UNTRUSTED"
    assert negative.median_dt_s is None
    assert negative.p95_dt_s is None
    assert "NEGATIVE_INTERVAL_PRESENT" in negative.reasons


def test_reboots_partition_time_domains_and_never_subtract_across_boots():
    capture = _real_capture()
    rows = list(capture.rows)
    split = 40
    rows = [
        dataclasses.replace(row, boot_id="boot-a" if index < split else "boot-b")
        for index, row in enumerate(rows)
    ]
    modified = dataclasses.replace(capture, rows=tuple(rows))
    sessions = analyze_sessions(modified)
    assert len(sessions) == 2
    assert sum(session.interval_stats.interval_count for session in sessions) == (
        len(rows) - len(sessions)
    )
    for session in sessions:
        assert session.interval_stats.time_base_status == (
            "TRUSTED_BOOT_SCOPED_UPTIME"
        )
    # The first session's last device_ms is never subtracted from the second's
    # first device_ms: the first session has split-1 intervals only.
    assert sessions[0].interval_stats.interval_count == split - 1
    assert sessions[0].interval_stats.observation_window_s == pytest.approx(
        (rows[split - 1].device_ms - rows[0].device_ms) / 1000.0
    )


def test_missing_time_base_returns_untrusted_without_host_time_substitution(
    tmp_path,
):
    rows = _row_overrides([1000, 2000, 3000])
    rows[1]["device_ms"] = ""
    export = _export(tmp_path, rows)
    analysis = analyze_capture(load_capture(export))
    stats = analysis.sessions[0].interval_stats
    assert stats.time_base_status == "TIME_BASE_UNTRUSTED"
    assert stats.median_dt_s is None
    assert stats.captured_frame_completeness is None
    assert stats.completeness_status == "NOT_ESTIMABLE"
    assert "TIME_BASE_UNTRUSTED" in {anomaly.code for anomaly in analysis.anomalies}


def test_partial_capture_cannot_claim_campaign_completeness(tmp_path):
    export = _export(tmp_path, _row_overrides(range(1000, 6000, 1000)))
    analysis = analyze_capture(load_capture(export))
    session = analysis.sessions[0]
    assert session.row_count == 5
    assert session.interval_stats.captured_frame_completeness == pytest.approx(1.0)
    assert session.interval_stats.completeness_status == "PROVISIONAL_DIAGNOSTIC"
    assert session.campaign_completeness == (
        "NOT_ESTIMABLE_ACQUISITION_BOUNDARIES_UNVERIFIED"
    )


def test_source_row_order_does_not_change_canonical_results(tmp_path):
    first = _export(tmp_path / "a", _row_overrides([0, 1000, 2000, 4000]))
    second = _export(
        tmp_path / "b",
        _row_overrides([0, 1000, 2000, 4000]),
        boot_id="boot-two",
    )
    analyses_forward = analyze_captures([load_capture(first), load_capture(second)])
    analyses_reverse = analyze_captures([load_capture(second), load_capture(first)])
    assert channel_summary_csv(analyses_forward) == channel_summary_csv(
        analyses_reverse
    )
    assert summarize_qa_suite(analyses_forward).to_dict() == summarize_qa_suite(
        analyses_reverse
    ).to_dict()


def test_config_validation_rejects_invalid_thresholds():
    assert "TOLERANCE_BAND_DEPARTURE" in QAConfig().to_dict()[
        "flatline_span_policy"
    ]
    with pytest.raises(ValueError):
        QAConfig(long_gap_ms=0).validate()
    with pytest.raises(ValueError):
        QAConfig(percentile_method="median").validate()
    with pytest.raises(ValueError):
        QAConfig(nominal_cadence_ms=0).validate()
    with pytest.raises(ValueError):
        QAConfig(flatline_min_span_s=-1.0).validate()


# ---------------------------------------------------------------------------
# channel quality
# ---------------------------------------------------------------------------


def test_missing_is_not_a_measured_zero(tmp_path):
    rows = _row_overrides([0, 1000, 2000])
    rows[0]["power_w"] = ""
    rows[1]["power_w"] = "0.0"
    rows[2]["power_w"] = "0.5"
    rows[0]["t1"] = ""
    rows[1]["t1"] = "0.0"
    rows[2]["t1"] = "20.0"
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    power = _channel(analysis, "cooling_power_w")
    assert power.present_count == 2
    assert power.missing_count == 1
    assert power.impossible_count == 0
    assert power.flatline_candidate_count is None
    t1 = _channel(analysis, "t1")
    assert t1.present_count == 2
    assert t1.missing_count == 1


def test_quality_states_are_counted_distinctly(tmp_path):
    rows = _row_overrides([0, 1000, 2000, 3000])
    for row, quality in zip(rows, ("VALID", "DEGRADED", "INVALID", "UNKNOWN")):
        row["thermal_quality"] = quality
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    t1 = _channel(analysis, "t1")
    assert (t1.quality_valid, t1.quality_degraded, t1.quality_invalid, t1.quality_unknown) == (
        1,
        1,
        1,
        1,
    )
    assert t1.diagnostic_status == "DIAGNOSTIC_CAUTION"
    assert "SOURCE_QUALITY_INVALID" in t1.reason_codes


def test_impossible_values_are_flagged_against_canonical_ranges(tmp_path):
    rows = _row_overrides([0, 1000])
    rows[0].update(
        {
            "t1": "200.0",
            "rh_pct": "150.0",
            "pressure_hpa": "50.0",
            "voltage_v": "400.0",
            "current_a": "60.0",
            "power_w": "20000.0",
            "energy_wh": "-1.0",
        }
    )
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    for channel in (
        "t1",
        "rh_pct",
        "pressure_hpa",
        "cooling_voltage_v",
        "cooling_current_a",
        "cooling_power_w",
        "cooling_energy_counter_wh",
    ):
        summary = _channel(analysis, channel)
        assert summary.impossible_count == 1, channel
        assert "IMPOSSIBLE_VALUE_OUTSIDE_INSTRUMENT_RANGE" in summary.reason_codes
        assert summary.diagnostic_status == "DIAGNOSTIC_CAUTION"


def test_flatline_candidate_versus_repeated_state_value(tmp_path):
    rows = _row_overrides(range(0, 20000, 1000))
    for row in rows:
        row["t1"] = "20.0"
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    t1 = _channel(analysis, "t1")
    assert t1.flatline_candidate_count == 1
    assert t1.repeated_equal_consecutive_count == 19
    assert t1.duplicate_identity_count == 0
    assert "FLATLINE_CANDIDATE_DIAGNOSTIC_ONLY" in t1.reason_codes
    applied = _channel(analysis, "applied_duty_permille")
    assert applied.flatline_candidate_count is None
    door = _channel(analysis, "door_state")
    assert door.flatline_candidate_count is None


def test_mid_session_plateau_is_a_flatline_candidate(tmp_path):
    rows = _row_overrides(range(0, 20000, 1000))
    for index, row in enumerate(rows):
        row["t1"] = "20.0" if index < 10 else "25.0"
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    t1 = _channel(analysis, "t1")
    assert t1.flatline_candidate_count == 2
    assert t1.repeated_equal_consecutive_count == 18


def test_state_channel_bounds_are_checked(tmp_path):
    capture = load_capture(_export(tmp_path, _row_overrides([0, 1000])))
    rows = list(capture.rows)
    rows[0] = dataclasses.replace(rows[0], requested_duty_permille=2000)
    rows[1] = dataclasses.replace(rows[1], requested_duty_permille=-1)
    modified = dataclasses.replace(capture, rows=tuple(rows))
    analysis = analyze_capture(modified)
    requested = _channel(analysis, "requested_duty_permille")
    assert requested.impossible_count == 2
    assert "IMPOSSIBLE_VALUE_OUTSIDE_INSTRUMENT_RANGE" in requested.reason_codes
    assert requested.diagnostic_status == "DIAGNOSTIC_CAUTION"


def test_flatline_minimum_span_is_configurable(tmp_path):
    rows = _row_overrides(range(0, 20000, 1000))
    for row in rows:
        row["t1"] = "20.0"
    capture = load_capture(_export(tmp_path, rows))
    analysis = analyze_capture(
        capture, config=QAConfig(flatline_min_span_s=100.0)
    )
    assert _channel(analysis, "t1").flatline_candidate_count == 0


def test_invalid_sections_split_flatline_spans(tmp_path):
    rows = _row_overrides(range(0, 21000, 1000))
    for row in rows:
        row["t1"] = "20.0"
    rows[10]["thermal_quality"] = "INVALID"
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    t1 = _channel(analysis, "t1")
    # 10 observations before and 10 after the INVALID row: two candidate spans.
    assert t1.flatline_candidate_count == 2


def test_stale_source_age_and_unavailable_age(tmp_path):
    rows = _row_overrides([0, 1000, 2000])
    rows[0]["t1_age_ms"] = "6000"
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    t1 = _channel(analysis, "t1")
    assert t1.stale_candidate_count == 1
    assert "SOURCE_AGE_EXCEEDS_DIAGNOSTIC_THRESHOLD" in t1.reason_codes
    t2 = _channel(analysis, "t2")
    assert t2.stale_candidate_count == 0

    c_analysis = analyze_capture(load_capture(C_FIXTURE))
    c_t1 = _channel(c_analysis, "t1")
    assert c_t1.stale_candidate_count is None
    assert "SOURCE_AGE_NOT_CARRIED" in c_t1.reason_codes


def test_duplicate_identity_is_not_repeated_temperature(tmp_path):
    rows = _row_overrides([0, 1000, 2000])
    rows[0]["dedup_key"] = "DUPLICATE-DELIVERY-KEY"
    rows[1]["dedup_key"] = "DUPLICATE-DELIVERY-KEY"
    for row in rows:
        row["t1"] = "20.0"
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    session = analysis.sessions[0]
    t1 = _channel(analysis, "t1")
    assert session.duplicate_identity_count == 1
    assert t1.duplicate_identity_count == 1
    assert t1.repeated_equal_consecutive_count == 2
    assert "DUPLICATE_IDENTITY_PRESENT" in {
        anomaly.code for anomaly in analysis.anomalies
    }


def test_duplicate_physical_identity_fails_closed_at_w04(tmp_path):
    rows = _row_overrides([0, 1000, 2000])
    rows[1]["seq"] = rows[0]["seq"]
    with pytest.raises(SourceRefusal) as excinfo:
        load_capture(_export(tmp_path, rows))
    assert excinfo.value.code == "SEQUENCE_CONTRADICTION"


def test_energy_counter_discontinuity_is_detected(tmp_path):
    rows = _row_overrides([0, 1000, 2000, 3000])
    for row, energy in zip(rows, ("1.0", "2.0", "1.5", "3.0")):
        row["energy_wh"] = energy
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    energy = _channel(analysis, "cooling_energy_counter_wh")
    assert energy.discontinuity_count == 1
    assert "COUNTER_DECREASE_OR_RESET" in energy.reason_codes


def test_pzem_unqualified_power_never_becomes_validated_energy(tmp_path):
    rows = _row_overrides([0, 1000])
    rows[0]["power_w"] = "84.9"
    rows[1]["power_w"] = "0.0"
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    power = _channel(analysis, "cooling_power_w")
    assert power.quality_valid == 0
    assert power.quality_unknown == 2
    assert power.diagnostic_status == "DIAGNOSTIC_READABLE_UNQUALIFIED"
    assert "PZEM_POWER_UNQUALIFIED_DIAGNOSTIC_ONLY" in power.reason_codes
    svg = render_physical_state_svg(
        analysis.capture, analysis.admission, analysis.sessions[0]
    )
    assert "UNQUALIFIED PZEM VALUES" in svg


def test_chamber_air_spread_excludes_t2(tmp_path):
    rows = _row_overrides([0, 1000, 2000])
    for row in rows:
        row.update({"t1": "20.0", "t2": "35.0", "t3": "20.1", "t4": "20.2"})
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    spread = analysis.sessions[0].chamber_air_spread
    assert spread is not None
    assert spread.slots == ("t1", "t3", "t4")
    assert spread.max_c == pytest.approx(0.2)
    assert set(spread.max_values) == {
        ("t1", 20.0),
        ("t3", 20.1),
        ("t4", 20.2),
    }


def test_t2_hot_side_is_separate_in_channels_and_plot():
    analysis = analyze_capture(_real_capture())
    assert analysis.capture.chamber_air_slots == ("t1", "t3", "t4")
    assert analysis.capture.hot_side_slots == ("t2",)
    svg = render_physical_state_svg(
        analysis.capture, analysis.admission, analysis.sessions[0]
    )
    panel_one = svg.split("Panel 2 — TEC hot-side", 1)[0]
    panel_two = svg.split("Panel 2 — TEC hot-side", 1)[1].split("Panel 3", 1)[0]
    assert "t2 (" not in panel_one
    assert "t2 (TEC_HOT_SIDE)" in panel_two


def test_absent_quality_domains_are_counted_unknown_not_valid():
    analysis = analyze_capture(load_capture(C_FIXTURE))
    assert analysis.statuses.channel_quality_status == "ATTENTION_REQUIRED"
    for name in ("door_state", "applied_duty_permille", "seq"):
        channel = _channel(analysis, name)
        assert channel.quality_domain is None
        assert channel.quality_valid == 0
        assert channel.quality_unknown == channel.row_count
        assert "QUALITY_DOMAIN_ABSENT_TREATED_AS_UNKNOWN" in channel.reason_codes
    # Domains the C snapshot does carry remain usable.
    t1 = _channel(analysis, "t1")
    assert t1.quality_domain == "thermal"
    assert t1.quality_valid == 1


def test_qualified_pzem_is_not_marked_unqualified(tmp_path):
    source_dir = tmp_path / "qualified"
    source_dir.mkdir(parents=True)
    source = _positive_export(source_dir)
    index = _positive_index(source_dir, valid=True)
    analysis = analyze_capture(load_capture(source, a_run_index=index))
    power = _channel(analysis, "cooling_power_w")
    assert power.quality_valid == power.row_count
    assert "PZEM_POWER_DOMAIN_VALID" in power.reason_codes
    assert "PZEM_POWER_UNQUALIFIED_DIAGNOSTIC_ONLY" not in power.reason_codes
    assert "PZEM_POWER_UNQUALIFIED" not in {
        anomaly.code for anomaly in analysis.anomalies
    }
    svg = render_physical_state_svg(
        analysis.capture, analysis.admission, analysis.sessions[0]
    )
    assert "UNQUALIFIED PZEM VALUES" not in svg
    out = tmp_path / "report"
    result = _run_cli(
        [
            "--source",
            str(source),
            "--a-run-index",
            str(index),
            "--out",
            str(out),
            "--format",
            "md",
        ]
    )
    assert result.returncode == 0, result.stderr
    markdown = (out / "qa-report-W05.md").read_text(encoding="utf-8")
    assert "UNQUALIFIED PZEM" not in markdown
    assert "PZEM qualification:" in markdown


def test_event_utc_with_unverified_sync_is_labeled(tmp_path):
    rows = _row_overrides([1000, 2000, 3000])
    for index, row in enumerate(rows):
        row["timestamp_utc"] = f"2026-01-01T00:00:0{index}Z"
        row["timestamp_utc_status"] = "AVAILABLE"
    export = _export(
        tmp_path,
        rows,
        timestamp_semantics={
            "timestamp_utc_status": "AVAILABLE",
            "timestamp_utc_source": "DEVICE_CLOCK_NO_SYNC_EVIDENCE",
            "measurement_time_axis": "DEVICE_UTC",
        },
    )
    analysis = analyze_capture(load_capture(export))
    stats = analysis.sessions[0].interval_stats
    assert stats.time_base_status == "EVENT_UTC_UNVERIFIED_SYNC"
    assert stats.median_dt_s == pytest.approx(1.0)
    assert "EVENT_TIME_SYNC_UNVERIFIED" in {
        anomaly.code for anomaly in analysis.anomalies
    }


def test_real_run_segments_and_chamber_air_spread():
    analysis = analyze_capture(_real_capture())
    session = analysis.sessions[0]
    assert [segment.run_id for segment in session.run_segments] == [
        "run-00000000",
        "run-00000001",
    ]
    assert [segment.row_count for segment in session.run_segments] == [226, 731]
    assert session.run_segments[1].start_s == pytest.approx(225.99)
    spread = session.chamber_air_spread
    assert spread is not None
    assert spread.slots == ("t1", "t3", "t4")
    assert spread.n == 957
    assert spread.min_c <= spread.median_c <= spread.p95_c <= spread.max_c
    assert spread.max_c == pytest.approx(1.126, abs=1e-6)
    assert {slot for slot, _value in spread.max_values} == {"t1", "t3", "t4"}
    svg = render_physical_state_svg(
        analysis.capture, analysis.admission, session
    )
    assert "source run_id segments (one boot; NOT independent)" in svg
    assert "time (s)" in svg
    parsed = _csv_rows(channel_summary_csv([analysis]))
    assert {row["run_segment_count"] for row in parsed} == {"2"}


def test_render_rejects_a_foreign_session(tmp_path):
    analysis = analyze_capture(_real_capture())
    other_dir = tmp_path / "other"
    other_dir.mkdir(parents=True)
    other = load_capture(_positive_export(other_dir))
    with pytest.raises(ValueError, match="not present"):
        render_physical_state_svg(
            other,
            analyze_capture(other).admission,
            analysis.sessions[0],
        )


def test_repeated_views_do_not_duplicate_channel_csv_rows():
    first = analyze_capture(_real_capture())
    second = analyze_capture(_real_capture())
    parsed = _csv_rows(channel_summary_csv([first, second]))
    assert len(parsed) == len(first.channels)


def test_partial_source_age_is_reported(tmp_path):
    rows = _row_overrides([0, 1000, 2000])
    rows[0]["t1_age_ms"] = ""
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    t1 = _channel(analysis, "t1")
    assert t1.stale_candidate_count == 0
    assert "SOURCE_AGE_PARTIAL" in t1.reason_codes


def test_c_source_does_not_require_unpromised_channels():
    analysis = analyze_capture(load_capture(C_FIXTURE))
    names = {channel.channel for channel in analysis.channels}
    assert {
        "t1",
        "t2",
        "t3",
        "t_air_c",
        "rh_pct",
        "cooling_voltage_v",
        "cooling_current_a",
        "cooling_power_w",
        "cooling_energy_counter_wh",
        "door_state",
        "applied_duty_permille",
        "applied_cooling_state",
        "seq",
        "event_time_utc",
    } <= names
    assert "pressure_hpa" not in names
    assert "requested_duty_permille" not in names
    assert "readback_duty_permille" not in names
    assert "door_polarity" not in names


def test_unknown_role_remains_unknown_in_c_fixture():
    analysis = analyze_capture(load_capture(C_FIXTURE))
    assert analysis.capture.chamber_air_slots == ()
    assert set(analysis.capture.unknown_role_slots) == {"t1", "t2", "t3"}
    t1 = _channel(analysis, "t1")
    assert t1.physical_role == "UNKNOWN_ROLE_NOT_CARRIED"
    assert "SENSOR_ROLE_UNKNOWN_OR_CONFLICTING" in {
        anomaly.code for anomaly in analysis.anomalies
    }
    svg = render_physical_state_svg(
        analysis.capture, analysis.admission, analysis.sessions[0]
    )
    assert "no role-qualified chamber-air channel" in svg


def test_door_unknown_is_not_interpreted_as_closed(tmp_path):
    rows = _row_overrides([0, 1000, 2000, 3000])
    rows[0]["door_open"] = "UNKNOWN"
    rows[0]["door_polarity"] = "UNCONFIRMED"
    analysis = analyze_capture(load_capture(_export(tmp_path, rows)))
    door = _channel(analysis, "door_state")
    assert door.present_count == 3
    assert door.unknown_state_count == 1
    assert door.missing_count == 0
    assert "DOOR_STATE_UNKNOWN_PRESENT" in door.reason_codes
    assert "DOOR_NO_OPEN_EVENT_IN_CAPTURE" in door.reason_codes
    assert any(
        anomaly.code == "DOOR_STATE_UNKNOWN_PRESENT"
        for anomaly in analysis.anomalies
    )


# ---------------------------------------------------------------------------
# plot/report integrity
# ---------------------------------------------------------------------------


def test_plot_segments_break_on_missing_and_long_gap():
    assert _segments(
        [0.0, 1.0, 2.0, 3.0, 4.0],
        [1.0, 2.0, None, 4.0, 5.0],
        [False, False, False, False, False],
        long_gap_s=10.0,
    ) == [[(0.0, 1.0), (1.0, 2.0)], [(3.0, 4.0), (4.0, 5.0)]]
    assert _segments(
        [0.0, 1.0, 10.0, 11.0],
        [1.0, 2.0, 3.0, 4.0],
        [False, False, False, False],
        long_gap_s=5.0,
    ) == [[(0.0, 1.0), (1.0, 2.0)], [(10.0, 3.0), (11.0, 4.0)]]
    assert all(
        value is not None
        for segment in _segments(
            [0.0, 1.0, 2.0],
            [1.0, None, 3.0],
            [False, False, False],
            long_gap_s=10.0,
        )
        for _time, value in segment
    )


def test_two_sources_are_not_merged_into_one_trajectory(tmp_path):
    first = _export(tmp_path / "a", _row_overrides([0, 1000, 2000]))
    second = _export(
        tmp_path / "b",
        _row_overrides([0, 1000, 2000]),
        boot_id="boot-two",
    )
    analyses = analyze_captures([load_capture(first), load_capture(second)])
    suite = summarize_qa_suite(analyses)
    assert suite.unique_physical_sources == 2
    assert suite.duplicate_views == 0
    assert sum(len(analysis.sessions) for analysis in analyses) == 2


def test_repeated_views_of_one_physical_source_do_not_inflate_n():
    first = _real_capture()
    second = _real_capture()
    suite = summarize_qa_suite(
        [analyze_capture(first), analyze_capture(second)]
    )
    assert suite.unique_physical_sources == 1
    assert suite.duplicate_views == 1
    assert suite.eligible_s1_runs == 0


def test_conflicting_duplicate_view_admissions_fail_closed(tmp_path):
    valid_dir = tmp_path / "valid"
    valid_dir.mkdir(parents=True)
    valid_capture = load_capture(
        _positive_export(valid_dir),
        a_run_index=_positive_index(valid_dir, valid=True),
    )
    invalid_dir = tmp_path / "invalid"
    invalid_dir.mkdir(parents=True)
    invalid_capture = load_capture(
        _positive_export(invalid_dir),
        a_run_index=_positive_index(invalid_dir, valid=False),
    )
    suite = summarize_qa_suite(
        [analyze_capture(valid_capture), analyze_capture(invalid_capture)]
    )
    assert suite.unique_physical_sources == 1
    assert suite.duplicate_views == 1
    assert suite.eligible_s1_runs == 0
    assert suite.predictive_dataset_readiness == "NOT_READY"
    assert len(suite.conflicts) == 1
    assert any(
        blocker["code"] == "DUPLICATE_VIEW_ADMISSION_CONFLICT"
        for blocker in suite.conflicts[0]["blockers"]
    )


def test_conflicting_duplicate_view_csv_fails_closed_and_is_order_independent(
    tmp_path,
):
    valid_view, invalid_view = _conflicting_views(tmp_path)
    first = analyze_captures([valid_view, invalid_view])
    second = analyze_captures([invalid_view, valid_view])

    first_csv = channel_summary_csv(first)
    second_csv = channel_summary_csv(second)
    assert first_csv == second_csv
    assert "ELIGIBLE_FOR_PREDICTIVE_DATASET" not in first_csv

    first_rows = _csv_rows(first_csv)
    assert len(first_rows) == len(first[0].channels)
    for row in first_rows:
        assert row["physical_admission_status"] == "EXCLUDED_OR_BLOCKED"
        assert "DUPLICATE_VIEW_ADMISSION_CONFLICT" in row["reason_codes"]

    first_suite = summarize_qa_suite(first)
    assert first_suite.predictive_dataset_readiness == "NOT_READY"
    assert first_suite.eligible_s1_runs == 0
    assert first_suite.eligible_s2_runs == 0
    assert len(first_suite.conflicts) == 1
    assert any(
        blocker["code"] == "DUPLICATE_VIEW_ADMISSION_CONFLICT"
        for blocker in first_suite.conflicts[0]["blockers"]
    )

    manifest = qa_manifest(
        first,
        first_suite,
        config=first[0].config,
        command="test",
        repository_revision="test",
        source_index=None,
    )
    view_statuses = [source["admission"]["status"] for source in manifest["sources"]]
    assert "ELIGIBLE_FOR_PREDICTIVE_DATASET" in view_statuses
    assert "EXCLUDED_OR_BLOCKED" in view_statuses
    assert any(
        blocker["code"] == "DUPLICATE_VIEW_ADMISSION_CONFLICT"
        for blocker in manifest["suite"]["conflicts"][0]["blockers"]
    )


def test_conflicting_duplicate_view_report_marks_view_verdict_non_authoritative(
    tmp_path,
):
    valid_view, invalid_view = _conflicting_views(tmp_path)
    analyses = analyze_captures([valid_view, invalid_view])
    suite = summarize_qa_suite(analyses)
    report = _cli_module()._render_markdown(
        analyses,
        suite,
        revision="test",
        command="test",
        output_label="test",
        code_sha256="0" * 64,
        source_index=None,
        plot_names=[[] for _ in analyses],
    )
    assert report.count("DUPLICATE_VIEW_ADMISSION_CONFLICT | TRUE") == 2
    assert report.count("| READY (VIEW ONLY; not the authoritative source verdict)") == 1
    assert "## 5. Duplicate-view admission conflicts" in report
    assert "| Adjudicated status |" in report
    assert report.count("| EXCLUDED_OR_BLOCKED | USABLE_FOR_DIAGNOSTIC_QA |") == 1


def test_single_eligible_view_keeps_its_csv_status(tmp_path):
    (tmp_path / "eligible").mkdir(parents=True)
    (tmp_path / "eligible-index").mkdir(parents=True)
    export = _positive_export(tmp_path / "eligible")
    view = load_capture(
        export,
        a_run_index=_positive_index(tmp_path / "eligible-index", valid=True),
    )
    analysis = analyze_capture(view)
    rows = _csv_rows(channel_summary_csv([analysis]))
    assert rows
    assert {
        row["physical_admission_status"] for row in rows
    } == {"ELIGIBLE_FOR_PREDICTIVE_DATASET"}
    assert all(
        "DUPLICATE_VIEW_ADMISSION_CONFLICT" not in row["reason_codes"]
        for row in rows
    )


def test_consistent_duplicate_views_collapse_once_in_csv():
    analysis = analyze_capture(_real_capture())
    duplicate = analyze_capture(_real_capture())
    assert channel_summary_csv([analysis, duplicate]) == channel_summary_csv(
        [analysis]
    )


def test_unrelated_devices_are_not_coalesced_in_csv(tmp_path):
    first = _export(tmp_path / "a", _row_overrides([0, 1000, 2000]))
    second = _export(
        tmp_path / "b",
        _row_overrides([0, 1000, 2000]),
        boot_id="boot-two",
    )
    analyses = analyze_captures([load_capture(first), load_capture(second)])
    rows = _csv_rows(channel_summary_csv(analyses))
    assert len({row["session_id"] for row in rows}) == 2
    assert len(rows) == sum(len(analysis.channels) for analysis in analyses)


def test_blocked_run_remains_blocked_in_manifest(tmp_path):
    analysis = analyze_capture(_real_capture())
    suite = summarize_qa_suite([analysis])
    manifest = qa_manifest(
        [analysis],
        suite,
        config=analysis.config,
        command="real-data-qa-v1.py --source evidence/A/W09/exports/CG-S1-H8C-600S.json",
        repository_revision="test-revision",
        source_index=None,
    )
    serialized = json.dumps(manifest, sort_keys=True)
    assert "EXCLUDED_OR_BLOCKED" in serialized
    assert manifest["suite"]["eligible_s1_runs"] == 0
    assert manifest["suite"]["predictive_dataset_readiness"] == "NOT_READY"
    assert "D:\\" not in serialized
    assert "/home/" not in serialized


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------


def test_cli_real_a_export_produces_all_artifacts(tmp_path):
    out = tmp_path / "out"
    result = _run_cli(
        [
            "--source",
            str(REAL_A_EXPORT),
            "--a-run-index",
            str(REAL_A_INDEX),
            "--out",
            str(out),
            "--format",
            "both",
        ]
    )
    assert result.returncode == 0, result.stderr
    for name in (
        "qa-report-W05.md",
        "qa-report-W05.html",
        "channel-summary.csv",
        "physical-state-W05.svg",
        "qa-manifest-W05.json",
    ):
        assert (out / name).is_file(), name
    markdown = (out / "qa-report-W05.md").read_text(encoding="utf-8")
    assert "Recorded rows | 957" in markdown
    assert "Analyzed boot sessions | 1" in markdown
    assert "A-valid S1 run IDs | 0" in markdown
    assert "W04 eligible S1 runs | 0" in markdown
    assert "Predictive dataset readiness | NOT_READY" in markdown
    assert "REAL MEASURED" in markdown
    assert "TEC_HOT_SIDE" in markdown
    assert "UNQUALIFIED PZEM" in markdown
    assert "Source run_id segments" in markdown
    assert "Chamber-air spread G_T" in markdown
    assert "D:\\" not in markdown
    manifest = json.loads(
        (out / "qa-manifest-W05.json").read_text(encoding="utf-8")
    )
    assert len(manifest["analysis_code_sha256"]) == 64
    assert manifest["analysis_code_sha256"] in markdown


def test_cli_c_fixture_is_supported(tmp_path):
    out = tmp_path / "c-out"
    result = _run_cli(
        [
            "--source",
            str(C_FIXTURE),
            "--out",
            str(out),
            "--format",
            "md",
        ]
    )
    assert result.returncode == 0, result.stderr
    assert (out / "qa-report-W05.md").is_file()
    assert (out / "channel-summary.csv").is_file()
    markdown = (out / "qa-report-W05.md").read_text(encoding="utf-8")
    assert "SYNTHETIC" in markdown
    assert "NOT_ESTIMABLE" in markdown
    assert "UNKNOWN_ROLE_NOT_CARRIED" in markdown


def test_cli_unsupported_source_returns_nonzero_with_reason(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"not": "a supported source"}', encoding="utf-8")
    out = tmp_path / "out"
    result = _run_cli(
        ["--source", str(bad), "--out", str(out), "--format", "md"]
    )
    assert result.returncode == 2
    assert "REFUSED" in result.stderr
    assert "UNRECOGNIZED_SOURCE_FORMAT" in result.stderr
    assert not out.exists()


def test_cli_multi_source_and_deterministic_replay(tmp_path):
    first = _export(tmp_path / "a", _row_overrides([0, 1000, 2000]))
    second = _export(
        tmp_path / "b",
        _row_overrides([0, 1000, 2000]),
        boot_id="boot-two",
    )
    out = tmp_path / "out"
    arguments = [
        "--source",
        str(first),
        "--source",
        str(second),
        "--out",
        str(out),
        "--format",
        "both",
    ]
    first_run = _run_cli(arguments)
    assert first_run.returncode == 0, first_run.stderr
    paths = sorted(
        path for path in out.iterdir() if path.is_file()
    )
    contents = {path.name: path.read_bytes() for path in paths}
    second_run = _run_cli(arguments)
    assert second_run.returncode == 0, second_run.stderr
    for path in paths:
        assert path.read_bytes() == contents[path.name], path.name
    report = (out / "qa-report-W05.md").read_text(encoding="utf-8")
    assert "Analyzed sources | 2" in report
    assert "Unique physical sources | 2" in report
    svg_files = sorted(out.glob("physical-state-W05-source*.svg"))
    assert len(svg_files) == 2


def test_cli_invalid_configuration_exits_one(tmp_path):
    result = _run_cli(
        [
            "--source",
            str(REAL_A_EXPORT),
            "--out",
            str(tmp_path / "out"),
            "--long-gap-ms",
            "0",
        ]
    )
    assert result.returncode == 1
    assert "CONFIGURATION_ERROR" in result.stderr
