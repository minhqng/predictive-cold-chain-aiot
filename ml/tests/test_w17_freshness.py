"""W17 freshness, late-arrival, PZEM/door trust and boot/reconnect proofs.

Matrix B (temporal correctness), C (sensor quality) and the door/electrical
rules of Doc 01/02 are exercised through the real replay API.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from coldguard_ml.feature_fixtures import (
    build_gap_trajectory,
    build_quality_degraded_trajectory,
    build_trajectory,
)
from coldguard_ml.feature_pipeline import FeaturePipelineError, PipelineSample
from coldguard_ml.feature_registry import FeatureRegistry, load_registry
from coldguard_ml.w15_artifact import load_guarded_artifact
from coldguard_ml.w17_shadow_parity import (
    DISPOSITIONS,
    READY_FOR_SOFTWARE_REPLAY,
    REFUSED_STALE_INPUT,
    REFUSED_TEMPORAL_ORDER,
    REFUSED_UNTRUSTED_INPUT,
    RUNTIME_FRESHNESS_POLICY_PENDING,
    SYNTHETIC_TEST_PARAMETER,
    FreshnessPolicy,
    ReplaySession,
    TelemetryRecord,
    W17IdentityError,
    W17TemporalError,
    run_shadow_parity,
)
from coldguard_ml.xgb_benchmark import (
    build_expanded_w11_fixture,
    load_benchmark_config,
)

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "reports" / "W15" / "model"


@pytest.fixture(scope="module")
def registry() -> FeatureRegistry:
    return load_registry(ROOT / "feature-registry-v1.yaml")


@pytest.fixture(scope="module")
def config(registry):
    return load_benchmark_config(ROOT / "xgb-v1-config.yaml", registry)


@pytest.fixture(scope="module")
def model(registry, config):
    return load_guarded_artifact(
        manifest_path=MODEL_DIR / "model-manifest-W15.json",
        model_path=MODEL_DIR / "model.ubj",
        expected_feature_ids=config.feature_policy.allowlist,
        expected_feature_schema_hash=registry.schema_sha256,
        expected_model_config_hash=config.config_sha256,
    )


def _session(trajectory, registry, model):
    return ReplaySession(
        template=trajectory,
        registry=registry,
        feature_ids=tuple(model.ordered_feature_ids),
    )


def _feed_all(session, trajectory, *, arrival=lambda sample: sample.time_s + 0.25):
    for sample in trajectory.samples:
        session.ingest(
            TelemetryRecord(sample=sample, arrival_time_s=arrival(sample))
        )


def _reasons(decision) -> dict[str, str | None]:
    if decision.vector is None:
        return {}
    return dict(zip(decision.vector.feature_ids, decision.vector.missing_reasons))


def _values(decision) -> dict[str, object]:
    if decision.vector is None:
        return {}
    return dict(zip(decision.vector.feature_ids, decision.vector.values))


@pytest.fixture(scope="module")
def s2_run():
    fixture = build_expanded_w11_fixture()
    return next(
        item
        for item in fixture.development_trajectories
        if item.scenario_id == "S2"
    )


@pytest.fixture(scope="module")
def unknown_door_run():
    trajectory, _ = build_trajectory(
        "CG-W17-UNK-UNIT-001",
        scenario="S2",
        seed=401,
        door_start_s=40.0,
        door_duration_s=20.0,
        unknown_start_s=80.0,
        unknown_duration_s=3.0,
        critical_offsets_s=(100.0,),
    )
    return trajectory


# ---------------------------------------------------------------------------
# B11-B14: future, late and out-of-order frames
# ---------------------------------------------------------------------------


def test_future_event_cannot_influence_a_past_anchor(
    s2_run, registry, model
):
    baseline = _session(s2_run, registry, model)
    for sample in s2_run.samples:
        if sample.time_s <= 40.0:
            baseline.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
    reference = baseline.feature_row_at(40.0, 41.0)
    with_future = _session(s2_run, registry, model)
    for sample in s2_run.samples:
        if sample.time_s <= 40.0:
            with_future.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
    source = next(sample for sample in s2_run.samples if sample.time_s == 100.0)
    forged = replace(
        source,
        seq=999,
        time_s=100.0,
        chamber_c=(
            ("CHAMBER_CENTER", 99.0),
            ("CHAMBER_BOTTOM", 99.0),
            ("CHAMBER_NEAR_DOOR", 99.0),
        ),
    )
    with_future.ingest(TelemetryRecord(sample=forged, arrival_time_s=100.25))
    decision = with_future.feature_row_at(40.0, 41.0)
    assert decision.ready
    assert decision.vector.sha256() == reference.vector.sha256()


def test_late_packet_cannot_rewrite_an_emitted_prediction(
    s2_run, registry, model
):
    session = _session(s2_run, registry, model)
    late_sample = next(sample for sample in s2_run.samples if sample.time_s == 30.0)
    for sample in s2_run.samples:
        if sample.time_s <= 60.0 and sample.time_s != 30.0:
            session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
    before = session.feature_row_at(40.0, 41.0)
    session.ingest(TelemetryRecord(sample=late_sample, arrival_time_s=60.0))
    after = session.feature_row_at(40.0, 41.0)
    assert before.vector.sha256() == after.vector.sha256()
    assert late_sample.identity in after.late_observation_ids
    later = session.feature_row_at(60.0, 61.0)
    assert late_sample.identity in later.input_telemetry_ids


def test_old_event_arriving_after_newer_one_is_deterministic(
    s2_run, registry, model
):
    baseline = _session(s2_run, registry, model)
    _feed_all(baseline, s2_run)
    baseline_decision = baseline.feature_row_at(60.0, 61.0)
    reordered = _session(s2_run, registry, model)
    samples = [
        sample for sample in s2_run.samples if sample.time_s <= 60.0
    ]
    for sample in samples[1:]:
        reordered.ingest(
            TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
        )
    reordered.ingest(
        TelemetryRecord(sample=samples[0], arrival_time_s=60.5)
    )
    decision = reordered.feature_row_at(60.0, 61.0)
    assert decision.ready
    assert decision.vector.sha256() == baseline_decision.vector.sha256()
    assert reordered.out_of_order_arrival_count == 1


def test_sequence_regression_with_newer_event_time_is_rejected(
    s2_run, registry, model
):
    session = _session(s2_run, registry, model)
    for sample in s2_run.samples:
        if sample.time_s != 10.0:
            session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
    newer = replace(
        next(sample for sample in s2_run.samples if sample.time_s == 10.0),
        time_s=181.0,
    )
    with pytest.raises(W17TemporalError):
        session.ingest(TelemetryRecord(sample=newer, arrival_time_s=181.25))
    decision = session.feature_row_at(181.0, 182.0)
    assert decision.disposition == REFUSED_TEMPORAL_ORDER


def test_sequence_regression_with_older_event_is_classified_late(
    s2_run, registry, model
):
    session = _session(s2_run, registry, model)
    for sample in s2_run.samples:
        if sample.time_s != 30.0:
            session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
    older = next(sample for sample in s2_run.samples if sample.time_s == 30.0)
    assert session.ingest(
        TelemetryRecord(sample=older, arrival_time_s=200.0)
    ) == "ACCEPTED"
    assert session.out_of_order_arrival_count == 1


def test_missing_event_time_is_never_inferred_from_arrival(
    s2_run, registry, model
):
    sample = s2_run.samples[0]
    with pytest.raises(FeaturePipelineError):
        replace(sample, time_s=float("nan"))
    with pytest.raises(ValueError):
        PipelineSample(
            device_id=sample.device_id,
            boot_id=sample.boot_id,
            seq=sample.seq,
            time_s=float("nan"),
            chamber_c=sample.chamber_c,
            hot_side_c=sample.hot_side_c,
            thermal_quality=sample.thermal_quality,
            door_state=sample.door_state,
            door_quality=sample.door_quality,
            door_polarity_attested=sample.door_polarity_attested,
            applied_cooling=sample.applied_cooling,
            applied_duty=sample.applied_duty,
            requested_duty_permille=sample.requested_duty_permille,
            readback_duty_permille=sample.readback_duty_permille,
            cooling_voltage_v=sample.cooling_voltage_v,
            cooling_current_a=sample.cooling_current_a,
            cooling_power_w=sample.cooling_power_w,
            cooling_energy_counter_wh=sample.cooling_energy_counter_wh,
            electrical_quality=sample.electrical_quality,
            t_air_c=sample.t_air_c,
            rh_pct=sample.rh_pct,
            environment_quality=sample.environment_quality,
            overall_quality=sample.overall_quality,
        )


# ---------------------------------------------------------------------------
# B15-B18: reconnect, boot and gaps
# ---------------------------------------------------------------------------


def test_reconnect_gap_is_refused_stale(s2_run, registry, model):
    session = _session(s2_run, registry, model)
    for sample in s2_run.samples:
        if sample.time_s <= 40.0:
            session.ingest(
                TelemetryRecord(sample=sample, arrival_time_s=sample.time_s + 0.25)
            )
    decision = session.feature_row_at(60.0, 61.0)
    assert decision.disposition == REFUSED_STALE_INPUT
    assert "ANCHOR_OBSERVATION_MISSING" in decision.reasons


def test_boot_boundary_clears_door_and_observation_state(
    s2_run, registry, model
):
    boot2_samples = tuple(
        replace(
            sample,
            boot_id="CG-W17-BOOT-2",
            seq=int(sample.time_s - 100.0),
            time_s=sample.time_s - 100.0,
        )
        for sample in s2_run.samples
        if 100.0 <= sample.time_s <= 120.0
    )
    boot2 = replace(
        s2_run,
        boot_id="CG-W17-BOOT-2",
        physical_source_key=s2_run.physical_source_key + ":BOOT-2",
        samples=boot2_samples,
    )
    session = _session(boot2, registry, model)
    _feed_all(session, boot2)
    decision = session.feature_row_at(5.0, 6.0)
    assert decision.ready
    reasons = _reasons(decision)
    assert reasons["time_since_open"] == "MISSING_NO_OBSERVED_TRANSITION"
    assert _values(decision)["door_open"] == 0.0


def test_cross_boot_frame_is_rejected(s2_run, registry, model):
    session = _session(s2_run, registry, model)
    foreign = replace(
        next(sample for sample in s2_run.samples if sample.time_s == 0.0),
        boot_id="CG-W17-BOOT-3",
    )
    with pytest.raises(W17IdentityError):
        session.ingest(TelemetryRecord(sample=foreign, arrival_time_s=0.25))
    decision = session.feature_row_at(0.0, 1.0)
    assert decision.disposition == "REFUSED_IDENTITY_MISMATCH"


def test_oversized_rolling_gap_is_not_bridged(registry, model):
    trajectory, _ = build_gap_trajectory()
    session = _session(trajectory, registry, model)
    _feed_all(session, trajectory)
    decision = session.feature_row_at(76.0, 77.0)
    assert decision.ready
    reasons = _reasons(decision)
    assert reasons["rolling_mean_temperature_60s"] == "MISSING_GAP"
    assert len(decision.input_telemetry_ids) == len(
        [sample for sample in trajectory.samples if sample.time_s <= 76.0]
    )


# ---------------------------------------------------------------------------
# C19-C25: PZEM, counter, door and partial-window trust
# ---------------------------------------------------------------------------


def test_stale_pzem_becomes_missing_not_zero(s2_run, registry, model):
    session = _session(s2_run, registry, model)
    for sample in s2_run.samples:
        session.ingest(
            TelemetryRecord(
                sample=sample,
                arrival_time_s=sample.time_s + 0.25,
                electrical_observed_at_s=sample.time_s - 30.0,
            )
        )
    decision = session.feature_row_at(100.0, 101.0)
    assert decision.disposition == REFUSED_STALE_INPUT
    reasons = _reasons(decision)
    values = _values(decision)
    assert reasons["cooling_power_w"] == "MISSING_ELECTRICAL_UNQUALIFIED"
    assert reasons["cooling_voltage_v"] == "MISSING_ELECTRICAL_UNQUALIFIED"
    assert values["cooling_power_w"] is None
    assert values["cooling_power_w"] != 0.0


def test_invalid_electrical_channel_is_not_trusted(registry, model):
    trajectory, _ = build_quality_degraded_trajectory()
    session = _session(trajectory, registry, model)
    _feed_all(session, trajectory)
    decision = session.feature_row_at(100.0, 101.0)
    assert decision.disposition == REFUSED_UNTRUSTED_INPUT
    assert "ELECTRICAL_QUALITY_INVALID" in decision.reasons


def test_counter_reset_does_not_create_negative_consumption(registry, model):
    trajectory, _ = build_trajectory(
        "CG-W17-COUNTER-UNIT-001",
        scenario="S2",
        seed=402,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(100.0,),
        counter_reset_at_s=70.0,
    )
    session = _session(trajectory, registry, model)
    _feed_all(session, trajectory)
    decision = session.feature_row_at(100.0, 101.0)
    assert decision.ready
    reasons = _reasons(decision)
    values = _values(decision)
    assert reasons["energy_counter_wh"] == "MISSING_COUNTER_RESET"
    assert values["energy_counter_wh"] is None
    integrated = values["past_integrated_cooling_energy_wh"]
    assert integrated is None or float(integrated) >= 0.0


def test_unknown_door_remains_missing_and_never_closed(
    unknown_door_run, registry, model
):
    session = _session(unknown_door_run, registry, model)
    _feed_all(session, unknown_door_run)
    decision = session.feature_row_at(80.0, 81.0)
    assert decision.disposition == REFUSED_UNTRUSTED_INPUT
    reasons = _reasons(decision)
    values = _values(decision)
    assert reasons["door_open"] == "MISSING_UNKNOWN_DOOR"
    assert reasons["duration_so_far"] == "MISSING_UNKNOWN_DOOR"
    assert values["door_open"] is None
    assert values["door_open"] != 0.0


def test_door_duration_is_not_carried_across_an_unknown_interruption(
    unknown_door_run, registry, model
):
    session = _session(unknown_door_run, registry, model)
    _feed_all(session, unknown_door_run)
    decision = session.feature_row_at(83.0, 84.0)
    assert decision.ready
    reasons = _reasons(decision)
    values = _values(decision)
    assert reasons["duration_so_far"] == "PRESENT"
    assert values["duration_so_far"] == 0.0
    assert values["door_open"] == 0.0
    assert values["time_since_open"] == pytest.approx(43.0)


def test_door_polarity_unattested_keeps_door_features_missing(registry, model):
    trajectory, _ = build_trajectory(
        "CG-W17-POLARITY-UNIT-001",
        scenario="S2",
        seed=403,
        door_start_s=40.0,
        door_duration_s=20.0,
        critical_offsets_s=(100.0,),
        door_polarity_attested=False,
    )
    session = _session(trajectory, registry, model)
    _feed_all(session, trajectory)
    decision = session.feature_row_at(100.0, 101.0)
    assert decision.disposition == REFUSED_UNTRUSTED_INPUT
    assert decision.reasons == ("DOOR_POLARITY_UNATTESTED",)
    assert _reasons(decision)["door_open"] == "MISSING_POLARITY_UNATTESTED"


def test_t2_hot_side_cannot_enter_the_chamber_aggregate(s2_run, registry, model):
    baseline = _session(s2_run, registry, model)
    _feed_all(baseline, s2_run)
    reference = baseline.feature_row_at(100.0, 101.0)
    mutated_trajectory = replace(
        s2_run,
        samples=tuple(
            replace(sample, hot_side_c=(sample.hot_side_c or 0.0) + 50.0)
            for sample in s2_run.samples
        ),
    )
    mutated = _session(mutated_trajectory, registry, model)
    _feed_all(mutated, mutated_trajectory)
    decision = mutated.feature_row_at(100.0, 101.0)
    assert "T_tec_hot_side_c" not in decision.vector.feature_ids
    assert decision.vector.sha256() == reference.vector.sha256()


def test_partial_or_untrusted_window_is_not_quietly_scored(
    unknown_door_run, registry, model
):
    result = run_shadow_parity(
        [unknown_door_run],
        registry,
        model=model,
        anchors_by_run={unknown_door_run.run_id: (79.0, 80.0, 83.0)},
    )
    assert result.feature_parity_verified
    assert ("REFUSED_UNTRUSTED_INPUT", 1) in result.refused_by_reason
    refused_records = [
        record
        for record in result.trace["records"]
        if record["prediction_anchor_event_s"] == 80.0
    ]
    assert len(refused_records) == 1
    record = refused_records[0]
    assert record["risk_score"] is None
    assert record["freshness"]["verdict"] == "REFUSED_UNTRUSTED_INPUT"
    assert record["hypothetical_warning"]["status"] == "WITHHELD_ANCHOR_REFUSED"


def test_freshness_policy_marker_and_vocabulary():
    policy = FreshnessPolicy()
    assert policy.policy_status == RUNTIME_FRESHNESS_POLICY_PENDING
    assert policy.parameter_class == SYNTHETIC_TEST_PARAMETER
    assert set(DISPOSITIONS) == {
        READY_FOR_SOFTWARE_REPLAY,
        REFUSED_STALE_INPUT,
        REFUSED_UNTRUSTED_INPUT,
        REFUSED_TEMPORAL_ORDER,
        "REFUSED_IDENTITY_MISMATCH",
        "REFUSED_FEATURE_SCHEMA_MISMATCH",
    }
    with pytest.raises(ValueError):
        FreshnessPolicy(policy_status="FROZEN")
