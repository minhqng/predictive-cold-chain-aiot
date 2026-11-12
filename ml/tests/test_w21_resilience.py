"""W21 SAFE_LOCAL, replay and recovery timeline controls."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from coldguard_ml.w21_resilience import (
    DURATION_ON_DEVICE_OBSERVED,
    DURATION_SOFTWARE_SIMULATION,
    EVIDENCE_HOST_SOFTWARE_SIMULATION,
    EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
    EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
    EXIT_REQUIREMENTS,
    PHYSICAL_STATE_NOT_VERIFIED,
    PHYSICAL_STATE_VERIFIED,
    REFUSAL_CLASS_NOT_PHYSICAL,
    REFUSAL_HOST_SIMULATION_TIME,
    STATUS_DETECTION_NOT_OBSERVED,
    STATUS_INVALID_ORDER,
    STATUS_OUTAGE_NOT_OBSERVED,
    STATUS_PHYSICAL_CONTROL_NOT_VERIFIED,
    STATUS_RESYNC_NOT_VERIFIED,
    STATUS_SAFE_LOCAL_STATE_NOT_VERIFIED,
    STATUS_TIME_DOMAIN_INSUFFICIENT,
    TIME_BACKEND_RECEIVED_AT,
    TIME_DEVICE_CAPTURED_AT,
    TIME_SOFTWARE_SIMULATION_CLOCK,
    TIME_UNKNOWN,
    TelemetryRecord,
    ResilienceTimeline,
    W21ResilienceError,
    assess_ai_fallback,
    assess_replay,
    assess_safe_local_exit,
    assess_stale_command,
    assess_timeline,
    population_distribution_status,
)

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)
SHA = "a" * 64


def _timeline(**overrides) -> ResilienceTimeline:
    payload = {
        "scenario_id": "FIXTURE-1",
        "source_id": "FIXTURE-SOURCE",
        "device_id": "d1",
        "boot_id": "b1",
        "time_domain": TIME_SOFTWARE_SIMULATION_CLOCK,
        "source_hash": SHA,
        "evidence_class": "HOST_SOFTWARE_SIMULATION",
        "outage_start": ORIGIN,
        "outage_end": ORIGIN + timedelta(seconds=120),
        "outage_detection": ORIGIN + timedelta(seconds=10),
        "safe_local_entered": ORIGIN + timedelta(seconds=10),
        "safe_local_exited": ORIGIN + timedelta(seconds=110),
        "local_control_state": "REACTIVE_HYSTERESIS",
        "physical_electrical_state": PHYSICAL_STATE_NOT_VERIFIED,
        "physical_thermal_state": PHYSICAL_STATE_NOT_VERIFIED,
        "physical_thermal_evidence_ref": None,
        "reconnect_observed": ORIGIN + timedelta(seconds=110),
        "fresh_state_confirmed": True,
        "resync_completed": ORIGIN + timedelta(seconds=130),
        "stale_command_rejected": True,
    }
    payload.update(overrides)
    return ResilienceTimeline(**payload)


def test_fixture_timeline_computes_declared_durations():
    assessment = assess_timeline(_timeline())
    assert assessment.durations["outage_duration_s"]["value_s"] == 120.0
    assert assessment.durations["detection_delay_s"]["value_s"] == 10.0
    assert assessment.durations["safe_local_interval_s"]["value_s"] == 100.0
    assert assessment.durations["reconnect_to_resync_s"]["value_s"] == 20.0
    assert all(
        value["duration_class"] == DURATION_SOFTWARE_SIMULATION
        for value in assessment.durations.values()
    )
    assert assessment.physical_thermal_protection is False
    assert STATUS_PHYSICAL_CONTROL_NOT_VERIFIED in assessment.statuses
    assert (
        "SAFE_LOCAL_SOFTWARE_STATE_IS_NOT_PHYSICAL_THERMAL_PROTECTION"
        in assessment.refusals
    )


def test_recorded_session_without_timestamps_is_fail_closed():
    timeline = _timeline(
        time_domain=TIME_DEVICE_CAPTURED_AT,
        outage_start=None,
        outage_end=None,
        outage_detection=None,
        safe_local_entered=None,
        safe_local_exited=None,
        reconnect_observed=None,
        fresh_state_confirmed=None,
        resync_completed=None,
        stale_command_rejected=None,
    )
    assessment = assess_timeline(timeline)
    assert assessment.durations == {}
    assert STATUS_OUTAGE_NOT_OBSERVED in assessment.statuses
    assert STATUS_DETECTION_NOT_OBSERVED in assessment.statuses
    assert STATUS_SAFE_LOCAL_STATE_NOT_VERIFIED in assessment.statuses
    assert STATUS_RESYNC_NOT_VERIFIED in assessment.statuses
    assert STATUS_PHYSICAL_CONTROL_NOT_VERIFIED in assessment.statuses
    assert assessment.physical_thermal_protection is False


def test_receipt_time_domain_is_refused():
    assessment = assess_timeline(_timeline(time_domain=TIME_BACKEND_RECEIVED_AT))
    assert STATUS_TIME_DOMAIN_INSUFFICIENT in assessment.statuses
    assert assessment.durations == {}


def test_unknown_time_domain_is_refused():
    assessment = assess_timeline(_timeline(time_domain=TIME_UNKNOWN))
    assert STATUS_TIME_DOMAIN_INSUFFICIENT in assessment.statuses
    assert assessment.durations == {}


def test_reversed_interval_is_invalid_not_negative():
    assessment = assess_timeline(
        _timeline(
            outage_start=ORIGIN + timedelta(seconds=10),
            outage_end=ORIGIN,
        )
    )
    assert STATUS_INVALID_ORDER in assessment.statuses
    assert "outage_duration_s" not in assessment.durations


def test_safe_local_without_exit_is_not_verified():
    assessment = assess_timeline(_timeline(safe_local_exited=None))
    assert STATUS_SAFE_LOCAL_STATE_NOT_VERIFIED in assessment.statuses
    assert "safe_local_interval_s" not in assessment.durations


def test_resync_without_fresh_state_is_not_verified():
    assessment = assess_timeline(_timeline(fresh_state_confirmed=False))
    assert STATUS_RESYNC_NOT_VERIFIED in assessment.statuses
    assert "NO_FRESH_STATE_EVIDENCE" in assessment.refusals


def test_reconnect_without_resync_timestamp_is_not_verified():
    assessment = assess_timeline(_timeline(resync_completed=None))
    assert STATUS_RESYNC_NOT_VERIFIED in assessment.statuses
    assert "reconnect_to_resync_s" not in assessment.durations


def test_physical_states_require_evidence_reference():
    no_ref = assess_timeline(
        _timeline(
            physical_electrical_state=PHYSICAL_STATE_VERIFIED,
            physical_thermal_state=PHYSICAL_STATE_VERIFIED,
        )
    )
    assert no_ref.physical_thermal_protection is False
    assert STATUS_PHYSICAL_CONTROL_NOT_VERIFIED in no_ref.statuses
    with_ref = assess_timeline(
        _timeline(
            evidence_class=EVIDENCE_OBSERVED_PHYSICAL_CONTROL_RESPONSE,
            physical_electrical_state=PHYSICAL_STATE_VERIFIED,
            physical_thermal_state=PHYSICAL_STATE_VERIFIED,
            physical_thermal_evidence_ref="raw://thermal-window-1",
        )
    )
    assert with_ref.physical_thermal_protection is True
    assert STATUS_PHYSICAL_CONTROL_NOT_VERIFIED not in with_ref.statuses


def test_host_simulation_cannot_produce_device_observed_duration():
    assessment = assess_timeline(
        _timeline(
            evidence_class=EVIDENCE_HOST_SOFTWARE_SIMULATION,
            time_domain=TIME_DEVICE_CAPTURED_AT,
        )
    )
    assert assessment.durations
    assert all(
        value["duration_class"] == DURATION_SOFTWARE_SIMULATION
        for value in assessment.durations.values()
    )
    assert REFUSAL_HOST_SIMULATION_TIME in assessment.refusals


def test_on_device_injection_cannot_claim_physical_protection():
    assessment = assess_timeline(
        _timeline(
            evidence_class=EVIDENCE_ON_DEVICE_SOFTWARE_INJECTION,
            time_domain=TIME_DEVICE_CAPTURED_AT,
            physical_electrical_state=PHYSICAL_STATE_VERIFIED,
            physical_thermal_state=PHYSICAL_STATE_VERIFIED,
            physical_thermal_evidence_ref="raw://thermal-window-1",
        )
    )
    assert all(
        value["duration_class"] == DURATION_ON_DEVICE_OBSERVED
        for value in assessment.durations.values()
    )
    assert assessment.physical_thermal_protection is False
    assert REFUSAL_CLASS_NOT_PHYSICAL in assessment.refusals
    assert STATUS_PHYSICAL_CONTROL_NOT_VERIFIED in assessment.statuses


def test_naive_datetime_is_rejected():
    with pytest.raises(W21ResilienceError):
        assess_timeline(_timeline(outage_start=datetime(2026, 1, 1)))
    with pytest.raises(W21ResilienceError):
        assess_timeline(_timeline(source_hash="nope"))


def _record(seq: int, digest: str, boot: str = "b1") -> TelemetryRecord:
    return TelemetryRecord(
        device_id="d1",
        boot_id=boot,
        seq=seq,
        captured_at=ORIGIN + timedelta(seconds=seq),
        received_at=ORIGIN + timedelta(seconds=seq + 1),
        payload_sha256=digest,
    )


def test_clean_replay_passes():
    assessment = assess_replay(
        [_record(1, "a" * 64), _record(2, "b" * 64)]
    )
    assert assessment.status == "VERIFIED"
    assert assessment.normalized_sample_count == 2
    assert assessment.duplicate_count == 0
    assert assessment.twin_regressions == 0


def test_duplicate_is_one_normalized_sample():
    assessment = assess_replay([_record(1, "a" * 64), _record(1, "a" * 64)])
    assert assessment.normalized_sample_count == 1
    assert assessment.duplicate_count == 1
    assert assessment.conflicting_duplicate_count == 0


def test_conflicting_duplicate_fails():
    assessment = assess_replay([_record(1, "a" * 64), _record(1, "b" * 64)])
    assert assessment.conflicting_duplicate_count == 1
    assert assessment.status == "FAILED"


def test_out_of_order_is_visible():
    assessment = assess_replay([_record(2, "a" * 64), _record(1, "b" * 64)])
    assert assessment.order_violation_count == 1
    assert assessment.status == "VERIFIED_WITH_OBSERVED_VARIATION"


def test_boot_change_is_a_new_stream():
    assessment = assess_replay(
        [_record(5, "a" * 64, "b1"), _record(1, "b" * 64, "b2")]
    )
    assert assessment.boot_change_count == 1
    assert assessment.normalized_sample_count == 2


def test_historical_replay_does_not_regress_twin():
    assessment = assess_replay(
        [_record(5, "a" * 64)], current_twin_seq={"b1": 10}
    )
    assert assessment.twin_regressions == 1
    assert assessment.status == "FAILED"


def test_missing_captured_at_refuses_receipt_substitution():
    record = TelemetryRecord(
        device_id="d1",
        boot_id="b1",
        seq=1,
        captured_at=None,
        received_at=ORIGIN,
        payload_sha256="a" * 64,
    )
    assessment = assess_replay([record])
    assert "RECEIPT_TIME_CANNOT_REPLACE_EVENT_TIME" in assessment.refusals
    assert assessment.missing_event_time_count == 1
    assert assessment.normalized_sample_count == 0
    assert assessment.status == "FAILED"


def test_sequence_gap_is_counted():
    assessment = assess_replay(
        [_record(1, "a" * 64), _record(2, "b" * 64), _record(5, "c" * 64)]
    )
    assert assessment.gap_count == 2
    assert assessment.status == "VERIFIED_WITH_OBSERVED_VARIATION"


def test_empty_replay_is_refused():
    with pytest.raises(W21ResilienceError):
        assess_replay([])


def test_stale_command_paths():
    expired = assess_stale_command(
        issued_at=ORIGIN,
        evaluated_at=ORIGIN + timedelta(seconds=60),
        ttl_s=10,
        fresh_state_confirmed=True,
        applied=False,
    )
    assert expired.status == "STALE_COMMAND_REJECTED"
    failed = assess_stale_command(
        issued_at=ORIGIN,
        evaluated_at=ORIGIN + timedelta(seconds=60),
        ttl_s=10,
        fresh_state_confirmed=True,
        applied=True,
    )
    assert failed.status == "FAILED"
    assert "STALE_COMMAND_MUST_NOT_BE_APPLIED" in failed.refusals
    held = assess_stale_command(
        issued_at=ORIGIN,
        evaluated_at=ORIGIN + timedelta(seconds=5),
        ttl_s=10,
        fresh_state_confirmed=False,
        applied=False,
    )
    assert held.status == "HELD_PENDING_FRESH_STATE"
    fresh = assess_stale_command(
        issued_at=ORIGIN,
        evaluated_at=ORIGIN + timedelta(seconds=5),
        ttl_s=10,
        fresh_state_confirmed=True,
        applied=True,
    )
    assert fresh.status == "FRESH"


def test_stale_command_rejects_bad_ttl_and_reversed_clock():
    with pytest.raises(W21ResilienceError):
        assess_stale_command(
            issued_at=ORIGIN,
            evaluated_at=ORIGIN,
            ttl_s=0,
            fresh_state_confirmed=True,
            applied=False,
        )
    with pytest.raises(W21ResilienceError):
        assess_stale_command(
            issued_at=ORIGIN + timedelta(seconds=5),
            evaluated_at=ORIGIN,
            ttl_s=10,
            fresh_state_confirmed=True,
            applied=False,
        )


def test_exit_gate_requires_every_condition():
    partial = {name: True for name in EXIT_REQUIREMENTS}
    partial["fresh_telemetry"] = False
    assessment = assess_safe_local_exit(partial, reconnect_observed=True)
    assert not assessment.ready
    assert assessment.missing == ("fresh_telemetry",)
    assert "RECONNECT_IS_NOT_SAFE_LOCAL_EXIT" in assessment.refusals
    assert "NO_FRESH_STATE_EVIDENCE" in assessment.refusals
    ready = assess_safe_local_exit(
        {name: True for name in EXIT_REQUIREMENTS}
    )
    assert ready.ready and ready.missing == () and ready.refusals == ()


def test_ai_fallback_never_trusts_a_stale_or_unavailable_score():
    ready = assess_ai_fallback(
        model_health="READY", risk_score_age_s=1.0, maximum_score_age_s=60.0
    )
    assert ready.score_usable is True
    unavailable = assess_ai_fallback(
        model_health="UNAVAILABLE", risk_score_age_s=0.0, maximum_score_age_s=60.0
    )
    assert unavailable.score_usable is False
    assert unavailable.status == "FALLBACK_REQUIRED"
    stale = assess_ai_fallback(
        model_health="READY", risk_score_age_s=120.0, maximum_score_age_s=60.0
    )
    assert stale.score_usable is False


def test_single_session_is_not_a_distribution():
    assert population_distribution_status(1) == "SINGLE_SESSION_IS_NOT_A_DISTRIBUTION"
    assert (
        population_distribution_status(2)
        == "ESTIMABLE_ONLY_WITH_ADMITTED_POPULATION_SUPPORT"
    )
