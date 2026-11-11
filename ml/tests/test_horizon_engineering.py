"""W13 horizon engineering: reconciliation, screening, study, decision, CLI.

Covers the twelve adversarial cases from the W13 task packet plus the
fail-closed provenance gate. The CLI replay tests consume the read-only
A 20261107 export and are skipped when it is absent (CI without the pinned
export); the module-level and constructed-package tests always run.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from coldguard_ml.feature_registry import load_registry
from coldguard_ml.grouped_evaluation import MetricValue, aggregate_fold_ap
from coldguard_ml.horizon_engineering import (
    CLASS_NOT_VERIFIED,
    DECISION_NO_SELECTION,
    DECISION_PRIMARY,
    DECISION_PROVISIONAL,
    POPULATION_REAL,
    POPULATION_SYNTHETIC,
    SCREEN_DEPRIORITIZED,
    SCREEN_PROVISIONAL,
    W13_LABEL_SPEC_VERSION,
    DatasetReconciliation,
    EvidencePinError,
    HorizonEngineeringError,
    PlantTiming,
    ReconciliationError,
    _xgb_fold,
    decide_primary_horizon,
    horizon_metrics_csv_rows,
    load_plant_timing,
    reconcile_a_dataset,
    run_horizon_study,
    screen_horizon_candidates,
    selection_preconditions,
    verify_sha256,
)
from coldguard_ml.labels import (
    CriticalEvent,
    CriticalEventSeries,
    LabelSpec,
    LabelStatus,
    generate_label_records,
)
from coldguard_ml.xgb_benchmark import (
    NON_ESTIMABLE_RUN_REASON,
    NonEstimableRunError,
    build_expanded_w11_fixture,
    load_benchmark_config,
    run_grouped_benchmark,
)

ML_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ML_ROOT / "scripts" / "horizon-study-W13.py"
CONFIG_PATH = ML_ROOT / "xgb-v1-config.yaml"
REGISTRY_PATH = ML_ROOT / "feature-registry-v1.yaml"
A_EXPORT = os.environ.get("COLDGUARD_W13_A_DATASET_DIR")
HAS_A_EXPORT = bool(A_EXPORT) and (Path(A_EXPORT) / "run_index.csv").is_file()
requires_a_export = pytest.mark.skipif(
    not HAS_A_EXPORT,
    reason=(
        "pinned A 20261107 export absent; set COLDGUARD_W13_A_DATASET_DIR to "
        "the read-only git-archive export to run the CLI replay proof"
    ),
)

# ---------------------------------------------------------------------------
# Constructed evidence packages (same schema as the merged A package)
# ---------------------------------------------------------------------------


def _timing(**overrides) -> PlantTiming:
    base = dict(
        evidence_kind="HOST_ANALYSIS_OF_COMMITTED_CAPTURES",
        physical_verified=False,
        command_to_electrical_s=1.094,
        electrical_n_measured=1,
        command_to_thermal_s=51.0,
        thermal_delta_c=1.0,
        cooling_tau_s=174.0,
        recovery_tau_s=86.0,
        tau_limitation="truncation-biased proxy",
        passive_drift_c=0.104,
        passive_window_min=3.633,
        door_to_critical_status="NOT_COMPUTABLE",
        door_to_critical_s=None,
        gaps=(),
    )
    base.update(overrides)
    return PlantTiming(**base)


def _timing_payload() -> dict:
    return {
        "command_to_electrical": {
            "n_measured": 1,
            "per_run": [{"delay_s": 1.094}],
        },
        "command_to_thermal": {
            "status": "MEASURED",
            "delay_s": 51.0,
            "delta_c": 1.0,
        },
        "cooling_tau": {"tau_s": 174.0, "limitation": "truncation-biased proxy"},
        "recovery_tau": {"tau_s": 86.0},
        "passive_proxy": {"passive_drift_c": 0.104, "passive_window_min": 3.633},
        "door_to_critical": {"status": "NOT_COMPUTABLE", "value_s": None},
        "evidence_kind": "HOST_ANALYSIS_OF_COMMITTED_CAPTURES",
        "physical_verified": False,
        "data_gap_register": [{"id": "GAP-DOOR-CRITICAL"}],
    }


def _row(
    tag: str,
    scenario: str,
    classification: str,
    boot: str,
    frames: int = 10,
    device_run_id: str = "UNSET",
) -> dict[str, str]:
    return {
        "run_tag": tag,
        "scenario": scenario,
        "classification": classification,
        "boot_id": boot,
        "device_run_id": device_run_id,
        "timebase": "HOST_STAMP",
        "device_timestamp_utc_source": "DEVICE_HAS_NO_WALL_CLOCK",
        "frames": str(frames),
        "dataset_path": f"datasets/{tag}-normalized.csv",
        "dataset_sha256": hashlib.sha256(tag.encode("utf-8")).hexdigest(),
    }


_INDEX_HEADER = (
    "run_tag,scenario,classification,boot_id,device_run_id,timebase,"
    "device_timestamp_utc_source,frames,dataset_path,dataset_sha256\n"
)


def _package(
    rows: list[dict[str, str]], manifest_rows: list[dict[str, str]] | None = None
) -> tuple[bytes, bytes]:
    index_text = _INDEX_HEADER + "".join(
        ",".join(row[column] for column in _INDEX_HEADER.strip().split(","))
        + "\n"
        for row in rows
    )
    pinned = rows if manifest_rows is None else manifest_rows
    manifest = {
        "totals": {
            "runs_and_segments": len(rows),
            "frames_total": sum(int(row["frames"]) for row in rows),
        },
        "outputs": [
            {"package_path": row["dataset_path"], "sha256": row["dataset_sha256"]}
            for row in pinned
        ],
    }
    return (
        index_text.encode("utf-8"),
        json.dumps(manifest, sort_keys=True).encode("utf-8"),
    )


_HEADER_WITH_TRACEABILITY = [
    "timestamp_utc",
    "event_time_utc",
    "timebase",
    "t1",
    "t2",
    "t3",
    "t4",
    "door_state",
    "calibration_id",
    "clock_sync",
]
_HEADER_WITHOUT_TRACEABILITY = ["timestamp_utc", "timebase", "t1", "t2", "t3", "t4"]


def _reconcile(
    rows: list[dict[str, str]],
    header=_HEADER_WITHOUT_TRACEABILITY,
    manifest_rows: list[dict[str, str]] | None = None,
):
    index_bytes, manifest_bytes = _package(rows, manifest_rows)
    return reconcile_a_dataset(
        index_bytes,
        manifest_bytes,
        normalized_header=header,
        timing=_timing(),
        run_index_sha256=hashlib.sha256(index_bytes).hexdigest(),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        source_revision="TEST-REVISION",
    )


def _real_like_rows() -> list[dict[str, str]]:
    """18 rows across 8 boots, mirroring the merged package's shape."""
    rows = [
        _row("W10-02", "S2_TIMING", "DATASET_ACCEPTED_S2", "73311d0c", 120),
        _row("W10-03-run1", "S2_DOOR", "DATASET_ACCEPTED_S2", "73311d0c", 300),
        _row("W10-03-run2", "S2_DOOR", "DATASET_ACCEPTED_S2", "73311d0c", 300),
        _row("W10-03-run3", "S2_DOOR", "DATASET_ACCEPTED_S2", "73311d0c", 300),
        _row("W10-03-run4", "S2_DOOR", "DATASET_ACCEPTED_S2", "73311d0c", 300),
        _row("S2-outside", "S2_OUTSIDE", "REAL_FRAMES_OUTSIDE_TIMED_WINDOWS", "73311d0c", 346),
        _row("trial2", "S1", "DATASET_ACCEPTED_S1", "4a21a645", 600),
        _row("trial3", "S1", "DATASET_ACCEPTED_S1", "4a21a645", 600),
        _row("trial4", "S1", "DATASET_ACCEPTED_S1", "4a21a645", 601),
        _row("S1-outside", "S1_OUTSIDE", "REAL_FRAMES_OUTSIDE_TIMED_WINDOWS", "4a21a645", 62),
        _row("trial1", "S1", "DATASET_ACCEPTED_S1", "c20d17f6", 600),
        _row("H8-C", "COOLING_STEP", "REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED", "56044b74", 957, "run-00000000"),
        _row("H8-E", "COOLING_STEP_1800S", "REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED", "c4ff0ab3", 2915, "run-00000000"),
        _row("w07-1", "W07_PASSIVE_REPEAT", "REAL_PHYSICAL_REPEATS / INDEPENDENCE_CAVEAT", "4b555191", 300),
        _row("w07-2", "W07_PASSIVE_REPEAT", "REAL_PHYSICAL_REPEATS / INDEPENDENCE_CAVEAT", "4b555191", 300),
        _row("w07-3", "W07_PASSIVE_REPEAT", "REAL_PHYSICAL_REPEATS / INDEPENDENCE_CAVEAT", "4b555191", 300),
        _row("step-2", "COOLING_STEP_500PERMILLE", "REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED", "be89bf4a", 196),
        _row("step-3", "COOLING_STEP_500PERMILLE", "REAL_PHYSICAL_RAW_COOLING / NOT_SCENARIO_QUALIFIED", "f44c9bed", 196),
    ]
    return rows


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def registry():
    return load_registry(REGISTRY_PATH)


@pytest.fixture(scope="module")
def config(registry):
    return load_benchmark_config(CONFIG_PATH, registry)


@pytest.fixture(scope="module")
def study(registry, config, tmp_path_factory):
    fixture = build_expanded_w11_fixture()
    out = tmp_path_factory.mktemp("w13-study")
    return run_horizon_study(fixture, registry, config, model_out_dir=out)


@pytest.fixture(scope="module")
def reconciliation():
    return _reconcile(_real_like_rows())


# ---------------------------------------------------------------------------
# Provenance pins and plant timing
# ---------------------------------------------------------------------------


def test_pin_mismatch_refuses_altered_evidence_bytes():
    payload = b"pinned evidence"
    digest = hashlib.sha256(payload).hexdigest()
    assert verify_sha256(payload, digest, "test") == digest
    with pytest.raises(EvidencePinError):
        verify_sha256(payload + b"x", digest, "test")


def test_plant_timing_refuses_non_measured_inputs():
    payload = _timing_payload()
    payload["command_to_electrical"]["n_measured"] = 0
    with pytest.raises(HorizonEngineeringError):
        load_plant_timing(payload)
    payload = _timing_payload()
    payload["command_to_thermal"]["status"] = "ESTIMATED"
    with pytest.raises(HorizonEngineeringError):
        load_plant_timing(payload)


def test_plant_timing_refuses_a_computed_door_to_critical_value():
    payload = _timing_payload()
    payload["door_to_critical"] = {"status": "COMPUTED", "value_s": 120.0}
    with pytest.raises(HorizonEngineeringError):
        load_plant_timing(payload)


def test_plant_timing_keeps_missing_door_to_critical_as_not_estimable():
    timing = load_plant_timing(_timing_payload())
    assert timing.door_to_critical_status == "NOT_COMPUTABLE"
    assert timing.door_to_critical_s is None


# ---------------------------------------------------------------------------
# Adversarial 1: 18 segments are not 18 independent runs
# ---------------------------------------------------------------------------


def test_eighteen_segments_are_not_eighteen_independent_runs(reconciliation):
    assert reconciliation.row_count == 18
    assert reconciliation.distinct_boots == 8
    assert reconciliation.predictive_eligible_runs == 0
    assert "SEGMENTS_SHARE_BOOTS_ROWS_ARE_NOT_INDEPENDENT_RUNS" in (
        reconciliation.refusal_reasons
    )
    assert reconciliation.to_dict()["verdict"] == "NO_RUN_ELIGIBLE_FOR_PREDICTIVE_DATASET"
    assert "8 distinct boots" in reconciliation.to_dict()["independence_statement"]
    assert "never counted as independent runs" in (
        reconciliation.to_dict()["independence_statement"]
    )


# ---------------------------------------------------------------------------
# Adversarial 2: unqualified physical data is never admitted
# ---------------------------------------------------------------------------


def test_traceability_absence_is_cited_and_never_admitted(reconciliation):
    assert "CALIBRATION_TRACEABILITY_ABSENT_FROM_PACKAGE_SCHEMA" in (
        reconciliation.refusal_reasons
    )
    assert "CLOCK_SYNC_NOT_EVIDENCED_IN_PACKAGE" in reconciliation.refusal_reasons
    assert reconciliation.predictive_eligible_runs == 0


def test_traceability_presence_still_refuses_predictive_admission():
    result = _reconcile(
        _real_like_rows(), header=_HEADER_WITH_TRACEABILITY
    )
    assert "CALIBRATION_TRACEABILITY_ABSENT_FROM_PACKAGE_SCHEMA" not in (
        result.refusal_reasons
    )
    assert "CLOCK_SYNC_NOT_EVIDENCED_IN_PACKAGE" not in result.refusal_reasons
    # EVENT_UTC, host-time, run identity, shared boots and the unfrozen
    # criterion still refuse every run.
    assert result.predictive_eligible_runs == 0
    for reason in (
        "EVENT_UTC_UNAVAILABLE_DEVICE_HAS_NO_WALL_CLOCK",
        "HOST_RECEIPT_TIME_IS_NOT_PHYSICAL_EVENT_TIME",
        "RUN_IDENTITY_UNRESOLVED_FOR_CG_RUN_PATTERN",
        "CRITICAL_CRITERION_AND_REPRESENTATIVE_T_NOT_FROZEN",
    ):
        assert reason in result.refusal_reasons


def test_reconciliation_refuses_inconsistent_or_unknown_packages():
    rows = _real_like_rows()
    index_bytes, manifest_bytes = _package(rows)
    with pytest.raises(ReconciliationError):
        reconcile_a_dataset(
            index_bytes,
            json.dumps({"totals": {"runs_and_segments": 1, "frames_total": 1}, "outputs": []}).encode(),
            normalized_header=_HEADER_WITH_TRACEABILITY,
            timing=_timing(),
            run_index_sha256=hashlib.sha256(index_bytes).hexdigest(),
            manifest_sha256=hashlib.sha256(
                json.dumps({"totals": {"runs_and_segments": 1, "frames_total": 1}, "outputs": []}).encode()
            ).hexdigest(),
        )
    unknown = _real_like_rows()
    unknown[0]["classification"] = "INVENTED_CLASS"
    with pytest.raises(ReconciliationError):
        _reconcile(unknown)
    drifted = _real_like_rows()
    drifted[0]["dataset_sha256"] = "0" * 64
    with pytest.raises(ReconciliationError):
        _reconcile(drifted, manifest_rows=_real_like_rows())


def test_reconcile_refuses_unpinned_looking_bytes():
    rows = _real_like_rows()
    index_bytes, manifest_bytes = _package(rows)
    with pytest.raises(EvidencePinError):
        reconcile_a_dataset(
            index_bytes,
            manifest_bytes,
            normalized_header=_HEADER_WITHOUT_TRACEABILITY,
            timing=_timing(),
            run_index_sha256="0" * 64,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        )


# ---------------------------------------------------------------------------
# Adversarial 12: stale A evidence never replaces the newer decision
# ---------------------------------------------------------------------------


def test_superseded_registries_are_noted_not_rewritten(reconciliation):
    notes = "\n".join(reconciliation.superseded_evidence_notes)
    assert "evidence/A/W09/run-registry.json" in notes
    assert "evidence/A/W11/additional-valid-run-list.json" in notes
    assert "superseded for scenario validity" in notes
    assert "does not grant B predictive eligibility" in notes


def test_stale_door_critical_reason_is_flagged_while_value_stands(reconciliation):
    assert reconciliation.s2_door_scenario_rows > 0
    notes = "\n".join(reconciliation.superseded_evidence_notes)
    assert "no door-open event exists in any committed capture" in notes
    assert "stale" in notes
    assert "NOT_COMPUTABLE value itself stands" in notes


def test_newer_decision_is_pinned_and_any_drift_refuses():
    # A stale or replaced evidence file cannot be consumed silently: any byte
    # drift from the pinned package fails the provenance gate.
    rows = _real_like_rows()
    index_bytes, manifest_bytes = _package(rows)
    index_sha = hashlib.sha256(index_bytes).hexdigest()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    reconcile_a_dataset(
        index_bytes,
        manifest_bytes,
        normalized_header=_HEADER_WITHOUT_TRACEABILITY,
        timing=_timing(),
        run_index_sha256=index_sha,
        manifest_sha256=manifest_sha,
    )
    with pytest.raises(EvidencePinError):
        reconcile_a_dataset(
            index_bytes.replace(b"W10-02", b"W10-XX", 1),
            manifest_bytes,
            normalized_header=_HEADER_WITHOUT_TRACEABILITY,
            timing=_timing(),
            run_index_sha256=index_sha,
            manifest_sha256=manifest_sha,
        )


def test_predictive_eligibility_is_derived_per_row():
    rows = _real_like_rows()
    admissible = rows[0]
    admissible["device_timestamp_utc_source"] = "DEVICE_UTC"
    admissible["timebase"] = "EVENT_UTC"
    admissible["device_run_id"] = "CG-S2-DOOR-001"
    index_bytes, manifest_bytes = _package(rows)
    common = dict(
        normalized_header=_HEADER_WITH_TRACEABILITY,
        timing=_timing(),
        run_index_sha256=hashlib.sha256(index_bytes).hexdigest(),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )
    admitted = reconcile_a_dataset(
        index_bytes, manifest_bytes, critical_criterion_frozen=True, **common
    )
    assert admitted.predictive_eligible_runs == 1
    frozen_refused = reconcile_a_dataset(index_bytes, manifest_bytes, **common)
    assert frozen_refused.predictive_eligible_runs == 0


def test_pr95_supplement_is_cited_never_consumed(reconciliation):
    pr95 = reconciliation.pr95_supplement
    assert pr95["merge_status"] == "OPEN_UNMERGED"
    assert pr95["classification"] == CLASS_NOT_VERIFIED
    assert pr95["consumed_as_canonical_evidence"] is False
    assert reconciliation.predictive_eligible_runs == 0


# ---------------------------------------------------------------------------
# Adversarial 3+4: label boundary and incomplete-horizon semantics
# ---------------------------------------------------------------------------


def _label_setup():
    base = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
    spec = LabelSpec(horizon_s=60.0, spec_version=W13_LABEL_SPEC_VERSION)
    return base, spec


def test_event_exactly_at_horizon_boundary_counts_and_at_prediction_does_not():
    base, spec = _label_setup()
    t = base + dt.timedelta(seconds=30)
    series = CriticalEventSeries(
        run_id="R1",
        events=(
            CriticalEvent(time=t, ref="AT_PREDICTION"),
            CriticalEvent(time=t + dt.timedelta(seconds=60), ref="AT_BOUNDARY"),
        ),
        series_id="S1",
        coverage_end=base + dt.timedelta(seconds=600),
    )
    record = generate_label_records(
        "R1", [(t, "anchor")], series, spec, coverage_end=series.coverage_end
    )[0]
    assert record.status is LabelStatus.EVALUABLE
    assert record.y == 1
    assert record.matched_event is not None
    assert record.matched_event.ref == "AT_BOUNDARY"

    only_at_prediction = CriticalEventSeries(
        run_id="R2",
        events=(CriticalEvent(time=t, ref="AT_PREDICTION"),),
        series_id="S2",
        coverage_end=base + dt.timedelta(seconds=600),
    )
    record = generate_label_records(
        "R2", [(t, "anchor")], only_at_prediction, spec, coverage_end=only_at_prediction.coverage_end
    )[0]
    assert record.status is LabelStatus.EVALUABLE
    assert record.y == 0


def test_incomplete_horizon_is_censored_never_negative():
    base, spec = _label_setup()
    t = base + dt.timedelta(seconds=30)
    series = CriticalEventSeries(run_id="R1", events=(), series_id="S1")
    record = generate_label_records(
        "R1",
        [(t, "anchor")],
        series,
        spec,
        coverage_end=t + dt.timedelta(seconds=59),
    )[0]
    assert record.status is LabelStatus.CENSORED
    assert record.y is None


def test_untrusted_event_in_horizon_is_untrusted_info():
    base, spec = _label_setup()
    t = base + dt.timedelta(seconds=30)
    series = CriticalEventSeries(
        run_id="R1",
        events=(
            CriticalEvent(
                time=t + dt.timedelta(seconds=10), trusted=False, ref="UNTRUSTED"
            ),
        ),
        series_id="S1",
        coverage_end=base + dt.timedelta(seconds=600),
    )
    record = generate_label_records(
        "R1", [(t, "anchor")], series, spec, coverage_end=series.coverage_end
    )[0]
    assert record.status is LabelStatus.UNTRUSTED_INFO
    assert record.y is None


# ---------------------------------------------------------------------------
# Adversarial 10: one-class AP is undefined, never comparative evidence
# ---------------------------------------------------------------------------


def test_single_class_ap_is_undefined_and_keeps_its_reason():
    aggregate = aggregate_fold_ap(
        [MetricValue(None, "SINGLE_CLASS_VALIDATION")]
    )
    assert aggregate["status"] == "UNDEFINED"
    fake_fold = SimpleNamespace(
        strategy="UNWEIGHTED",
        fold_id="F1",
        status="FIT",
        reason=None,
        metrics={
            "average_precision": {
                "value": None,
                "status": "UNDEFINED",
                "reason": "SINGLE_CLASS_VALIDATION",
            },
            "undefined_reasons": ["SINGLE_CLASS_VALIDATION"],
        },
        event_metrics=None,
    )
    fold = _xgb_fold(fake_fold)
    assert fold.average_precision.value is None
    assert "SINGLE_CLASS_VALIDATION" in fold.undefined_reasons
    assert aggregate_fold_ap([fold.average_precision])["status"] == "UNDEFINED"


# ---------------------------------------------------------------------------
# Adversarial 6+7: EWT/AIW are never zero; screening is derived
# ---------------------------------------------------------------------------


def test_screening_deprioritizes_30s_and_stays_provisional_elsewhere():
    timing = load_plant_timing(_timing_payload())
    screenings = {item.horizon_s: item for item in screen_horizon_candidates(timing)}
    assert screenings[30.0].screen == SCREEN_DEPRIORITIZED
    assert screenings[30.0].aiw_upper_bound_s == -21.0
    for horizon, bound in ((60.0, 9.0), (120.0, 69.0), (300.0, 249.0)):
        assert screenings[horizon].screen == SCREEN_PROVISIONAL
        assert screenings[horizon].aiw_upper_bound_s == bound
        assert screenings[horizon].status == "DERIVED_PROXY_SCREENING_NOT_A_MEASURED_VERDICT"
    assert len(screenings[60.0].caveats) == 4
    with pytest.raises(HorizonEngineeringError):
        screen_horizon_candidates(timing, (0.0,))


# ---------------------------------------------------------------------------
# Study integration (synthetic development population)
# ---------------------------------------------------------------------------


def test_study_covers_candidates_and_refuses_zero_sample_horizon(study):
    assert [item.horizon_s for item in study.horizons] == [30.0, 60.0, 120.0, 300.0]
    for item in study.horizons:
        assert item.label_identity["horizon_s"] == item.horizon_s
        assert item.label_identity["spec_version"] == W13_LABEL_SPEC_VERSION
        assert item.ewt_status == "NOT_ESTIMABLE"
        assert item.aiw_status == "NOT_ESTIMABLE"
        assert item.ewt_reason_code and item.aiw_reason_code
    complete = [item for item in study.horizons if item.horizon_s < 300.0]
    for item in complete:
        assert item.leakage_audit_status == "PASS"
        assert item.method_folds
        assert item.refusal_reason is None
        # Split happens before window generation and every overlapping
        # window stays inside its run's partition; the locked test is never
        # read by the horizon study.
        assert item.leakage_probes.get("split_before_windows") == "PASS"
        assert item.leakage_probes.get("grouped_disjoint") == "PASS"
        assert item.leakage_probes.get("pair_preservation") == "PASS"
        assert item.leakage_probes.get("locked_test") == "PASS"
    refused = study.horizons[-1]
    assert refused.leakage_audit_status == "NOT_RUN_HORIZON_REFUSED"
    assert refused.method_folds == ()
    assert refused.aggregate_ap == {}
    assert refused.refusal_reason and "W13_HORIZON_NOT_ESTIMABLE" in refused.refusal_reason
    assert "DEV_RUN_WITHOUT_EVALUABLE_ANCHORS" in refused.refusal_reason
    assert "max()" not in refused.refusal_reason
    assert "defect stays open" not in refused.refusal_reason
    # The H=300 population is single-class positive; negatives are zero, not
    # fabricated, and censored anchors are excluded rather than labeled 0.
    assert refused.negative_count == 0
    assert refused.positive_count > 0
    assert refused.censored_exclusions > 0


def test_h300_population_is_refused_by_the_shared_benchmark(registry, config, tmp_path):
    fixture = build_expanded_w11_fixture()
    variant = dataclasses.replace(
        config,
        label=dataclasses.replace(
            config.label,
            horizon_s=300.0,
            spec_version=W13_LABEL_SPEC_VERSION,
        ),
    )
    with pytest.raises(NonEstimableRunError) as caught:
        run_grouped_benchmark(fixture, registry, variant, out_dir=tmp_path)
    assert caught.value.reason_code == NON_ESTIMABLE_RUN_REASON
    assert len(caught.value.runs) == 8
    assert all(reasons.get("CENSORED", 0) > 0 for _, reasons in caught.value.runs)


def test_study_never_reads_the_locked_test(study):
    assert study.split_identity["test_partition_used"] is False
    assert study.limitations
    assert any("locked" in item for item in study.limitations)


def test_study_is_reproducible_in_memory(study, registry, config, tmp_path):
    fixture = build_expanded_w11_fixture()
    again = run_horizon_study(fixture, registry, config, model_out_dir=tmp_path)
    assert again.to_dict() == study.to_dict()


def test_frozen_label_configuration_is_refused_by_the_study(
    registry, config, tmp_path
):
    frozen = dataclasses.replace(
        config,
        label=dataclasses.replace(
            config.label,
            boundary_c=5.0,
            frozen_at=dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc),
        ),
    )
    with pytest.raises(HorizonEngineeringError):
        run_horizon_study(
            build_expanded_w11_fixture(), registry, frozen, model_out_dir=tmp_path
        )


# ---------------------------------------------------------------------------
# Adversarial 11: populations are never hidden in one table
# ---------------------------------------------------------------------------


def test_csv_keeps_populations_apart_and_real_rows_are_refusals(
    study, reconciliation
):
    rows = horizon_metrics_csv_rows(study, reconciliation)
    assert {row["population"] for row in rows} == {
        POPULATION_SYNTHETIC,
        POPULATION_REAL,
    }
    real_rows = [row for row in rows if row["population"] == POPULATION_REAL]
    assert len(real_rows) == 4
    for row in real_rows:
        assert row["row_type"] == "REAL_REFUSAL"
        assert row["average_precision"] is None
        assert row["ap_status"] == "NOT_ESTIMABLE"
        assert row["event_recall"] is None
        assert row["ewt_status"] == "NOT_ESTIMABLE"
        assert row["aiw_status"] == "NOT_ESTIMABLE"
        assert "EVENT_UTC_UNAVAILABLE" in row["ap_reason"]
    for row in rows:
        if row["population"] == POPULATION_SYNTHETIC:
            assert row["scientific_claim_status"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
            assert "origin/main@" not in str(row["provenance"])


# ---------------------------------------------------------------------------
# Adversarial 8+9: decision gate
# ---------------------------------------------------------------------------


def _reconciliation(eligible: int) -> DatasetReconciliation:
    return DatasetReconciliation(
        source_revision="TEST-REVISION",
        run_index_sha256="a" * 64,
        manifest_sha256="b" * 64,
        sources=(),
        row_count=0,
        distinct_boots=0,
        frames_total=0,
        accepted_s1_windows=0,
        accepted_s2_windows=0,
        s2_door_scenario_rows=0,
        predictive_eligible_runs=eligible,
        refusal_reasons=(),
        superseded_evidence_notes=(),
        pr95_supplement={},
    )


def _frozen_config(config):
    return dataclasses.replace(
        config,
        label=dataclasses.replace(
            config.label,
            boundary_c=5.0,
            frozen_at=dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc),
        ),
    )


def test_synthetic_ap_never_selects_a_primary_horizon(
    study, reconciliation, config
):
    # The synthetic study reaches AP=1.0 at every fold of both XGB
    # strategies; the decision must still refuse to select.
    best = max(
        (
            fold.average_precision.value
            for metrics in study.horizons
            for fold in metrics.method_folds
            if fold.average_precision.value is not None
        ),
        default=None,
    )
    assert best == 1.0
    screenings = screen_horizon_candidates(load_plant_timing(_timing_payload()))
    decision = decide_primary_horizon(
        study, reconciliation, _timing(), config, screenings
    )
    assert decision.category == DECISION_PROVISIONAL
    assert decision.primary_horizon_s is None
    assert decision.provisional_candidates_s == (60.0, 120.0, 300.0)
    assert decision.deprioritized_s == (30.0,)
    assert "real_eligible_predictive_runs" in decision.blockers
    assert decision.selection_preconditions["locked_test_untouched"] is True
    assert decision.to_dict()["freeze_status"] == "NOT_FROZEN"


def test_primary_requires_every_precondition_and_a_unique_real_candidate(
    study, config
):
    screenings = screen_horizon_candidates(load_plant_timing(_timing_payload()))
    measured_timing = _timing(
        door_to_critical_status="COMPUTED", door_to_critical_s=110.0
    )
    eligible = _reconciliation(1)
    decision = decide_primary_horizon(
        study,
        eligible,
        measured_timing,
        _frozen_config(config),
        screenings,
        selection_rule_frozen=True,
        latency_chain_measured=True,
        real_horizon_metrics={60.0: {"average_precision": 0.42, "aiw_positive": True}},
    )
    assert decision.category == DECISION_PRIMARY
    assert decision.primary_horizon_s == 60.0

    ambiguous = decide_primary_horizon(
        study,
        eligible,
        measured_timing,
        _frozen_config(config),
        screenings,
        selection_rule_frozen=True,
        latency_chain_measured=True,
        real_horizon_metrics={
            60.0: {"average_precision": 0.42, "aiw_positive": True},
            120.0: {"average_precision": 0.51, "aiw_positive": True},
        },
    )
    assert ambiguous.primary_horizon_s is None
    assert "REAL_CANDIDATE_NOT_UNIQUE_UNDER_FROZEN_RULE" in ambiguous.blockers

    touched = dataclasses.replace(
        study,
        split_identity={**study.split_identity, "test_partition_used": True},
    )
    preconditions = selection_preconditions(
        touched,
        eligible,
        measured_timing,
        _frozen_config(config),
        selection_rule_frozen=True,
        latency_chain_measured=True,
    )
    assert preconditions["locked_test_untouched"] is False
    blocked = decide_primary_horizon(
        touched,
        eligible,
        measured_timing,
        _frozen_config(config),
        screenings,
        selection_rule_frozen=True,
        latency_chain_measured=True,
        real_horizon_metrics={60.0: {"average_precision": 0.42, "aiw_positive": True}},
    )
    assert blocked.category != DECISION_PRIMARY
    assert "locked_test_untouched" in blocked.blockers


def test_no_selection_when_no_candidate_survives_screening(study, reconciliation, config):
    timing = _timing(command_to_thermal_s=400.0)
    screenings = screen_horizon_candidates(timing, (30.0, 60.0, 120.0, 300.0))
    decision = decide_primary_horizon(study, reconciliation, timing, config, screenings)
    assert decision.category == DECISION_NO_SELECTION
    assert decision.display_category == "NO_SELECTION — INSUFFICIENT EVIDENCE"
    assert decision.primary_horizon_s is None


# ---------------------------------------------------------------------------
# CLI: fail-closed behavior and pinned-evidence replay
# ---------------------------------------------------------------------------


def _run_cli(out: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ML_ROOT / "src")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--repository-revision",
            "TEST-REVISION",
            *extra,
        ],
        cwd=ML_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_cli_refuses_missing_evidence_and_clears_stale_artifacts(tmp_path):
    out = tmp_path / "W13"
    out.mkdir()
    stale = out / "horizon-study.md"
    stale.write_text("stale package", encoding="utf-8")
    completed = _run_cli(out, "--a-dataset-dir", str(tmp_path / "missing"))
    assert completed.returncode == 2
    assert "W13 REFUSED" in completed.stderr
    assert not stale.exists()


@requires_a_export
def test_cli_writes_consistent_manifest_with_honest_statuses(tmp_path):
    out = tmp_path / "W13"
    completed = _run_cli(out, "--a-dataset-dir", A_EXPORT)
    assert completed.returncode == 0, completed.stderr
    manifest = json.loads(
        (out / "horizon-manifest-W13.json").read_text(encoding="utf-8")
    )
    for name, entry in manifest["artifacts"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == entry["sha256"]
    assert manifest["deterministic"] is True
    assert manifest["generated_at_utc"] == "NOT_RECORDED_BY_DESIGN"
    assert manifest["scientific_verdicts"]["W13_SOFTWARE"] == "GREEN"
    assert (
        manifest["scientific_verdicts"]["HORIZON_EVALUATION_COMPLETENESS"]
        == "PARTIAL_3_OF_4_HORIZONS"
    )
    assert (
        manifest["scientific_verdicts"]["W11_PIPELINE_DEFECT"]
        == "REPAIRED_EMPTY_RUN_POPULATION_REFUSAL_IN_W11"
    )
    assert (
        manifest["scientific_verdicts"]["HORIZON_DECISION"]
        == "PROVISIONAL_CANDIDATE_ONLY"
    )
    assert manifest["scientific_verdicts"]["PRIMARY_HORIZON_FROZEN"] == "NOT_FROZEN"
    assert manifest["scientific_verdicts"]["LOCKED_TEST"] == "UNTOUCHED"
    assert manifest["decision"]["primary_horizon_s"] is None
    assert manifest["reconciliation"]["predictive_eligible_runs"] == 0
    assert manifest["reconciliation"]["row_count"] == 18
    assert manifest["reconciliation"]["distinct_boots"] == 8
    assert manifest["plant_timing"]["door_to_critical_s"] is None
    assert len(
        manifest["repository_inputs"]["a_20261107_package"]["dataset_csv_sha256"]
    ) == 18
    assert manifest["hard_boundaries"]
    csv_text = (out / "horizon-metrics.csv").read_text(encoding="utf-8")
    assert "REAL_REFUSAL" in csv_text
    assert "NOT_ESTIMABLE" in csv_text
    for cells in csv.reader(csv_text.splitlines()[1:]):
        lowered = {cell.strip().lower() for cell in cells}
        assert "nan" not in lowered and "none" not in lowered


@requires_a_export
def test_cli_replay_is_byte_deterministic(tmp_path):
    out = tmp_path / "W13"
    first = _run_cli(out, "--a-dataset-dir", A_EXPORT)
    assert first.returncode == 0, first.stderr
    names = (
        "horizon-study.md",
        "horizon-metrics.csv",
        "primary-horizon-decision.md",
        "horizon-manifest-W13.json",
    )
    snapshot = {name: (out / name).read_bytes() for name in names}
    second = _run_cli(out, "--a-dataset-dir", A_EXPORT)
    assert second.returncode == 0, second.stderr
    for name, payload in snapshot.items():
        assert (out / name).read_bytes() == payload, name


@requires_a_export
def test_cli_refuses_a_tampered_timing_report(tmp_path):
    payload = json.loads(
        (ML_ROOT.parent / "evidence/A/W13/plant-timing-report.json").read_text(
            encoding="utf-8"
        )
    )
    payload["command_to_thermal"]["delay_s"] = 5.0
    tampered = tmp_path / "plant-timing-report.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    completed = _run_cli(
        tmp_path / "W13",
        "--a-dataset-dir",
        A_EXPORT,
        "--a-timing-report",
        str(tampered),
    )
    assert completed.returncode == 2
    assert "W13 REFUSED" in completed.stderr