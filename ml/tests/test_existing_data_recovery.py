"""Adversarial probes for the existing-data recovery core (probes 1-22)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from coldguard_ml import existing_data_recovery as recovery
from coldguard_ml.horizon_engineering import ReconciledSource


BOOT = "b0000001"
SHA_A = "a" * 64
SHA_B = "b" * 64


def _row(**overrides: str) -> dict[str, str]:
    base = {
        "run_tag": "r1",
        "scenario": "S1",
        "boot_id": BOOT,
        "seq": "1",
        "uptime_ms": "1000",
        "t1_c": "30.0",
        "t1_status": "OK",
        "t2_c": "29.8",
        "t2_status": "OK",
        "t3_c": "29.9",
        "t3_status": "OK",
        "t4_c": "30.1",
        "t4_status": "OK",
        "door_open": "0.0",
        "door_status": "OK",
        "current_a": "0.0",
        "current_status": "OK",
        "power_w": "0.0",
        "power_status": "OK",
        "energy_wh": "1.0",
        "pwm_applied_permille": "0.0",
        "quality": "OK",
    }
    base.update(overrides)
    return base


def _rows(count: int = 2, **overrides: str) -> list[dict[str, str]]:
    rows = []
    for index in range(count):
        row = _row(**overrides)
        row["seq"] = str(index + 1)
        row["uptime_ms"] = str(1000 + index * 1000)
        rows.append(row)
    return rows


def _reconciled_source(
    *, run_tag: str = "r1", boot: str = BOOT, scenario: str = "S1"
) -> ReconciledSource:
    return ReconciledSource(
        run_tag=run_tag,
        scenario=scenario,
        a_classification="DATASET_ACCEPTED_S1"
        if scenario == "S1"
        else "DATASET_ACCEPTED_S2",
        boot_id=boot,
        device_run_id="UNSET",
        timebase="HOST_STAMP",
        device_timestamp_utc_source="DEVICE_HAS_NO_WALL_CLOCK",
        frames=2,
        dataset_path=f"datasets/{run_tag}.csv",
        dataset_sha256=SHA_A,
        b_classification="PHYSICAL_BUT_NOT_ELIGIBLE",
        permitted_use="SCENARIO_QA_AND_BASELINE_CHARACTERIZATION",
    )


def _record(
    *,
    run_tag: str = "r1",
    boot: str = BOOT,
    scenario: str = "S1",
    rows: list[dict[str, str]] | None = None,
    shared_boot: bool = True,
    exact_duplicates: int = 0,
):
    source = _reconciled_source(run_tag=run_tag, boot=boot, scenario=scenario)
    run_row = {
        "frames": str(len(rows or _rows())),
        "device_run_id": "UNSET",
        "raw_source": "",
        "hardware_config_id": "CG-HW-001",
        "firmware_version": "cg-w06-0.1.0",
    }
    return recovery.build_a_source_record(
        source,
        run_row=run_row,
        rows=rows or _rows(),
        dataset_dir=Path("."),
        source_revision="FIXTURE",
        raw_source_sha256=None,
        shared_boot=shared_boot,
        source_path_prefix="fixture-dataset",
        exact_duplicate_rows=exact_duplicates,
    )


def _reconciliation(row_count: int = 2, frames_total: int = 4):
    return SimpleNamespace(
        row_count=row_count,
        frames_total=frames_total,
        accepted_s1_windows=row_count,
        accepted_s2_windows=0,
        predictive_eligible_runs=0,
        source_revision="FIXTURE",
        run_index_sha256=SHA_A,
        manifest_sha256=SHA_B,
    )


def _manifest():
    return {"totals": {"runs_and_segments": 2, "frames_total": 4}}


# Probe 1
def test_correct_physical_source_is_recognized():
    record = _record()
    assert record.source_id == "A20261107:r1"
    assert record.metrics.air is not None
    assert record.metrics.air.valid_frames == 2
    assert record.current_verified_disposition == recovery.USE_DESCRIPTION


# Probe 2
def test_incorrect_sha256_fails():
    with pytest.raises(recovery.EvidencePinError):
        recovery.verify_sha256(b"altered", SHA_A, "fixture")


# Probe 3
def test_duplicate_segments_are_detected():
    rows = [_row(seq="1"), _row(seq="1"), _row(seq="2")]
    kept, duplicates = recovery.deduplicate_rows(rows, "fixture")
    assert duplicates == 1
    assert len(kept) == 2
    contradictory = [_row(seq="1"), _row(seq="1", t1_c="31.0")]
    with pytest.raises(recovery.DuplicateSourceError):
        recovery.deduplicate_rows(contradictory, "fixture")
    first = _record(run_tag="r1")
    second = _record(run_tag="r2")
    assert recovery.detect_duplicate_records([first, second]) == [
        ("A20261107:r1", "A20261107:r2")
    ]


# Probe 4
def test_two_windows_sharing_one_boot_are_not_independent_runs():
    first = _record(run_tag="r1", boot=BOOT)
    second = _record(run_tag="r2", boot=BOOT)
    totals = recovery.family_totals(
        [first, second],
        reconciliation=_reconciliation(row_count=2, frames_total=4),
        manifest=_manifest(),
    )
    assert totals["distinct_boots"] == 1
    assert totals["independent_sessions"] == 1
    assert totals["independent_qualified_runs"] == 0
    assert first.counts_as_independent_experiment is False
    assert second.counts_as_independent_experiment is False


# Probe 5
def test_unmerged_a_evidence_is_not_promoted():
    record = _record()
    inventory = recovery.build_inventory(
        a_records=[record],
        w05_record=None,
        w21_record=None,
        reconciliation=_reconciliation(row_count=1, frames_total=2),
        manifest=_manifest(),
        unavailable=[],
        source_inputs=[],
        a_dataset_label="fixture-dataset",
        a_package_pins={"source_revision": "FIXTURE"},
    )
    pr95 = next(
        item
        for item in inventory["packaging_aliases"]
        if item["alias_id"] == "PR95:SUPPLEMENT"
    )
    assert pr95["classification"] == "UNMERGED_SUPPLEMENTARY_EVIDENCE"
    assert pr95["consumed_as_canonical"] is False
    assert pr95["counts_as_independent"] is False
    assert pr95["trial_json_sha256"] == recovery.PR95_TRIAL_SHA256


# Probe 6 is an integration probe in the delivery test module.


# Probe 7
def test_t2_hot_side_is_excluded_from_chamber_air():
    cool = _row(t2_c="10.0")
    hot = _row(t2_c="60.0")
    assert recovery._chamber_air(cool) == recovery._chamber_air(hot)
    rows = [_rows(1, t2_c="10.0")[0], _rows(1, t2_c="60.0")[0]]
    metrics = recovery.build_metrics(rows, source_id="fixture")
    assert metrics.air is not None
    assert metrics.air.mean_c == pytest.approx(30.0)
    assert metrics.t2 is not None
    assert metrics.t2.mean_c == pytest.approx(35.0)


# Probe 8
def test_invalid_temperature_is_not_converted_into_zero():
    rows = [
        _row(seq="1", t1_c="", t1_status="OK"),
        _row(seq="2", t1_c="30.0", t1_status="INVALID"),
        _row(seq="3", t1_c="", t1_status=""),
    ]
    stats = recovery.summarize_channel(
        rows,
        lambda row: recovery._slot_value(row, "t1"),
        lambda row: recovery._slot_status(row, "t1"),
        times=[1.0, 2.0, 3.0],
    )
    assert stats.valid_frames == 0
    assert stats.missing_frames == 2
    assert stats.status_not_ok_frames == 1
    assert stats.mean_c is None
    assert stats.mean_c != 0.0


# Probe 9
def test_missing_pzem_current_is_not_zero_amperes():
    rows = [
        _row(
            seq="1",
            pwm_applied_permille="1000",
            current_a="",
            current_status="OK",
            power_w="",
            power_status="",
            energy_wh="",
        ),
        _row(
            seq="2",
            pwm_applied_permille="1000",
            current_a="",
            current_status="OK",
            power_w="",
            power_status="",
            energy_wh="",
        ),
    ]
    cooling = recovery.detect_cooling_phase(rows, [1.0, 2.0], source_id="fixture")
    assert cooling is not None
    assert cooling.current_mean_a is None
    assert cooling.power_mean_w is None
    assert cooling.energy_delta_wh is None


# Probe 10
def test_unknown_door_is_not_interpreted_as_closed():
    rows = [
        _row(seq="1", door_open="UNKNOWN", door_status="UNVERIFIED"),
        _row(seq="2", door_open="UNKNOWN", door_status="UNVERIFIED"),
        _row(seq="3", door_open="0.0", door_status="UNVERIFIED"),
    ]
    assert recovery._door_state(rows[0]) is None
    assert recovery._door_state(rows[2]) is None
    assert recovery.detect_door_events(rows, [1.0, 2.0, 3.0], source_id="fixture") == ()


def test_door_pre_during_post_sample_counts_are_reported():
    rows = _rows(70, door_status="OK")
    for index in (30, 31):
        rows[index]["door_open"] = "1.0"
    events = recovery.detect_door_events(
        rows,
        [float(index + 1) for index in range(len(rows))],
        source_id="fixture",
    )
    assert len(events) == 1
    event = events[0]
    assert event.pre_frames == 30
    assert event.during_frames == 2
    assert event.post_frames == 30
    assert event.frame_count == 2


# Probe 11
def test_invalid_sensor_period_is_excluded_and_disclosed():
    rows = [
        _row(seq="1", t3_c="29.9", t3_status="INVALID"),
        _row(seq="2", t3_c="29.9", t3_status="OK"),
    ]
    stats = recovery.summarize_channel(
        rows,
        lambda row: recovery._slot_value(row, "t3"),
        lambda row: recovery._slot_status(row, "t3"),
        times=[1.0, 2.0],
    )
    assert stats.valid_frames == 1
    assert stats.status_not_ok_frames == 1
    assert stats.total_frames == 2


# Probe 12
def test_boot_relative_time_is_not_labelled_absolute():
    rows = _rows(2)
    _times, domain, note = recovery.time_axis(rows)
    start, end = recovery._time_bounds(rows, prefer_host=False)
    assert domain == "BOOT_SCOPED_UPTIME"
    assert start["kind"] == "BOOT_SCOPED_UPTIME"
    assert start["physical_event_time"] is False
    assert end["physical_event_time"] is False
    assert "not an absolute" in note


# Probe 13
def test_source_without_event_identity_cannot_acquire_a_door_event():
    rows = _rows(5, door_open="0.0", door_status="OK")
    events = recovery.detect_door_events(rows, [1.0, 2.0, 3.0, 4.0, 5.0], source_id="s1")
    assert events == ()
    record = _record(rows=rows)
    questions = {
        item.key: item
        for item in recovery._eight_questions(record)
    }
    assert questions["disturbance"].answer == "NO"


# Probe 14
def test_single_physical_session_is_not_a_statistical_population():
    record = _record(run_tag="r1", boot=BOOT)
    totals = recovery.family_totals(
        [record],
        reconciliation=_reconciliation(row_count=1, frames_total=2),
        manifest=_manifest(),
    )
    assert totals["independent_sessions"] == 1
    assert totals["predictive_eligible_runs"] == 0
    assert "never independent runs" in totals["independence_statement"]


# Probe 15
def test_no_label_is_fabricated_from_an_unfrozen_threshold():
    assessment = recovery.assess_predictive([_record()])
    assert assessment.overall == "NOT_ESTIMABLE"
    assert assessment.exploratory_metrics == "NOT_ESTIMABLE"
    assert assessment.overall_reasons
    question = next(
        item
        for item in assessment.sources[0]["questions"]
        if item["key"] == "label"
    )
    assert question["answer"] == "NO"


# Probe 16
def test_future_features_are_refused():
    recovery.assert_feature_time_before_target(9.0, 10.0)
    with pytest.raises(recovery.FutureFeatureRefused):
        recovery.assert_feature_time_before_target(10.0, 10.0)
    with pytest.raises(recovery.FutureFeatureRefused):
        recovery.assert_feature_time_before_target(11.0, 10.0)


# Probe 17
def test_train_test_source_overlap_is_refused():
    recovery.assert_disjoint_train_test(["boot-a"], ["boot-b"])
    with pytest.raises(recovery.SourceOverlapRefused):
        recovery.assert_disjoint_train_test(["boot-a", "boot-b"], ["boot-b"])


# Probe 18
def test_single_class_average_precision_stays_undefined():
    assert recovery.safe_average_precision([1, 1, 1], [0.9, 0.8, 0.7]) is None
    assert recovery.safe_average_precision([0, 0], [0.9, 0.8]) is None
    assert recovery.safe_average_precision([]) is None
    assert recovery.safe_average_precision([0, 1, 1], [0.1, 0.9, 0.8]) == pytest.approx(1.0)
    assert recovery.safe_average_precision([0, 1, 0], [0.9, 0.8, 0.1]) == pytest.approx(0.5)


# Probe 19
def test_synthetic_average_precision_is_not_reported_as_physical():
    recovery.promote_metric_to_physical(
        recovery.EVIDENCE_PHYSICAL, "average_precision"
    )
    with pytest.raises(recovery.SyntheticMetricPromotionRefused):
        recovery.promote_metric_to_physical(
            recovery.EVIDENCE_SYNTHETIC, "average_precision"
        )


# Probe 20
def test_w15_risk_score_is_not_a_calibrated_probability():
    assert recovery.w15_score_semantics() == "RISK_SCORE_ONLY"
    assert recovery.w15_score_semantics() != "CALIBRATED_PROBABILITY"


# Probe 21
def test_incomplete_feature_input_does_not_produce_a_trusted_prediction():
    ready, missing = recovery.ready_for_w15_scoring(["T_chamber_max_c"])
    assert ready is False
    assert "frozen_target_label" not in missing  # the label is not a feature
    assert "ambient_temperature_c" in missing
    assert "relative_humidity_pct" in missing


# Probe 22
def test_w16_locked_test_path_is_never_opened():
    with pytest.raises(recovery.SourcePathRefused):
        recovery.validate_source_inputs(
            {
                "schema": recovery.INPUT_INVENTORY_SCHEMA,
                "sources": [
                    {
                        "source_id": "HARMFUL",
                        "kind": "A_DATASET_MANIFEST",
                        "path": "ml/reports/W16/locked-test-manifest-W16.json",
                        "expected_sha256": SHA_A,
                        "required": True,
                        "root": "REPOSITORY",
                    }
                ],
            }
        )
