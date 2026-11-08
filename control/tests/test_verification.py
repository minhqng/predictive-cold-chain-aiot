import pytest
from dataclasses import replace
from coldguard_control import (
    VerificationPolicy,
    VerificationObservation,
    VerificationTracker,
    CoolingHealthState,
    EnvelopeQualification,
    QualityState,
    CoolingState,
)
from coldguard_control.types import VerificationState
from coldguard_control.config import ConfigError

def make_policy(qualification=EnvelopeQualification.CANDIDATE_UNQUALIFIED):
    return VerificationPolicy(
        policy_version="v0",
        envelope_id="env-001",
        qualification=qualification,
        active_current_min_a=7.0,
        active_current_max_a=10.0,
        off_current_max_a=0.1,
        electrical_window_s=2.0,
        thermal_window_s=5.0,
        thermal_min_drop_c=1.0,
        active_power_min_w=(50.0 if qualification is EnvelopeQualification.QUALIFIED else None),
        active_power_max_w=(100.0 if qualification is EnvelopeQualification.QUALIFIED else None),
        source="test",
    )

def test_verification_unqualified_stops_at_unknown():
    policy = make_policy()
    tracker = VerificationTracker(
        policy,
        command_id="cmd-001",
        action=CoolingState.ON,
        started_s=0.0,
        baseline_temperature_c=30.0,
    )
    # Provide electrical observation inside active envelope
    obs1 = VerificationObservation(
        now_s=0.5,
        current_a=8.0,
        current_quality=QualityState.VALID,
        power_w=None,
        power_quality=QualityState.UNKNOWN,
        thermal_t_representative_c=None,
        thermal_quality=QualityState.UNKNOWN,
        applied_cooling=CoolingState.ON,
    )
    snap1 = tracker.observe(obs1)
    assert snap1.state == VerificationState.UNKNOWN
    # Provide thermal observation achieving drop
    obs2 = VerificationObservation(
        now_s=3.0,
        current_a=None,
        current_quality=QualityState.UNKNOWN,
        power_w=None,
        power_quality=QualityState.UNKNOWN,
        thermal_t_representative_c=28.5,  # drop 1.5°C from baseline 30
        thermal_quality=QualityState.VALID,
    )
    snap2 = tracker.observe(obs2)
    # Since envelope is unqualified, state should be UNKNOWN, not VERIFIED
    assert snap2.state == VerificationState.UNKNOWN
    assert snap2.health == CoolingHealthState.UNKNOWN


def test_tick_without_fresh_electrical_coverage_is_unknown():
    tracker = VerificationTracker(
        make_policy(EnvelopeQualification.QUALIFIED),
        command_id="cmd-tick", action=CoolingState.ON, started_s=0.0,
    )
    tracker.observe(VerificationObservation(
        now_s=0.5, current_a=1.0, current_quality=QualityState.VALID,
        applied_cooling=CoolingState.ON,
    ))
    snap = tracker.tick(3.0)
    assert snap.state is VerificationState.UNKNOWN
    assert not snap.electrical_response_observed


def test_unqualified_failure_stays_unknown():
    tracker = VerificationTracker(
        make_policy(), command_id="cmd-candidate", action=CoolingState.ON,
        started_s=0.0,
    )
    tracker.observe(VerificationObservation(
        now_s=0.5, current_a=1.0, current_quality=QualityState.VALID,
        applied_cooling=CoolingState.ON,
    ))
    snap = tracker.tick(3.0)
    assert snap.state is VerificationState.UNKNOWN
    assert snap.health is CoolingHealthState.UNKNOWN


def test_late_electrical_sample_cannot_verify_on():
    tracker = VerificationTracker(
        make_policy(EnvelopeQualification.QUALIFIED),
        command_id="cmd-late-current", action=CoolingState.ON, started_s=0.0,
    )
    snap = tracker.observe(VerificationObservation(
        now_s=2.1, current_a=8.0, current_quality=QualityState.VALID,
        applied_cooling=CoolingState.ON,
    ))
    assert snap.state is VerificationState.UNKNOWN
    assert not snap.electrical_response_observed


def test_late_thermal_sample_cannot_verify_on():
    tracker = VerificationTracker(
        make_policy(EnvelopeQualification.QUALIFIED),
        command_id="cmd-late-thermal", action=CoolingState.ON, started_s=0.0,
        baseline_temperature_c=30.0,
    )
    tracker.observe(VerificationObservation(
        now_s=0.5, current_a=8.0, current_quality=QualityState.VALID,
        power_w=80.0, power_quality=QualityState.VALID,
        applied_cooling=CoolingState.ON,
    ))
    snap = tracker.observe(VerificationObservation(
        now_s=5.6, thermal_t_representative_c=28.0,
        thermal_quality=QualityState.VALID,
    ))
    assert snap.state is VerificationState.UNKNOWN
    assert not snap.thermal_response_observed


def test_missing_required_power_is_unknown():
    policy = VerificationPolicy(
        policy_version="v0", envelope_id="env-power",
        qualification=EnvelopeQualification.QUALIFIED,
        active_current_min_a=7.0, active_current_max_a=10.0,
        off_current_max_a=0.1, electrical_window_s=2.0,
        thermal_window_s=5.0, thermal_min_drop_c=1.0,
        active_power_min_w=50.0, active_power_max_w=100.0,
        source="test",
    )
    tracker = VerificationTracker(
        policy, command_id="cmd-no-power", action=CoolingState.ON,
        started_s=0.0,
    )
    tracker.observe(VerificationObservation(
        now_s=0.5, current_a=8.0, current_quality=QualityState.VALID,
        applied_cooling=CoolingState.ON,
    ))
    snap = tracker.tick(2.1)
    assert snap.state is VerificationState.UNKNOWN
    assert snap.health is CoolingHealthState.UNKNOWN


def test_thermal_without_baseline_is_unknown():
    tracker = VerificationTracker(
        make_policy(EnvelopeQualification.QUALIFIED),
        command_id="cmd-no-baseline", action=CoolingState.ON, started_s=0.0,
    )
    tracker.observe(VerificationObservation(
        now_s=0.5, current_a=8.0, current_quality=QualityState.VALID,
        power_w=80.0, power_quality=QualityState.VALID,
        applied_cooling=CoolingState.ON,
    ))
    tracker.observe(VerificationObservation(
        now_s=2.0, thermal_t_representative_c=28.0,
        thermal_quality=QualityState.VALID,
    ))
    snap = tracker.tick(5.6)
    assert snap.state is VerificationState.UNKNOWN


def test_observation_cannot_precede_last_tick():
    tracker = VerificationTracker(
        make_policy(EnvelopeQualification.QUALIFIED),
        command_id="cmd-clock", action=CoolingState.ON, started_s=0.0,
    )
    tracker.tick(1.0)
    with pytest.raises(ValueError, match="backwards"):
        tracker.observe(VerificationObservation(now_s=0.5))


def test_healthy_response_requires_applied_on_feedback():
    tracker = VerificationTracker(
        make_policy(EnvelopeQualification.QUALIFIED),
        command_id="cmd-no-applied", action=CoolingState.ON, started_s=0.0,
    )
    tracker.observe(VerificationObservation(
        now_s=0.5, current_a=8.0, current_quality=QualityState.VALID,
        power_w=80.0, power_quality=QualityState.VALID,
        thermal_t_representative_c=30.0, thermal_quality=QualityState.VALID,
    ))
    tracker.observe(VerificationObservation(
        now_s=1.0, thermal_t_representative_c=28.0,
        thermal_quality=QualityState.VALID,
    ))
    snap = tracker.tick(2.1)
    assert snap.state is VerificationState.UNKNOWN
    assert snap.health is CoolingHealthState.UNKNOWN


def test_valid_applied_and_thermal_observations_can_verify():
    tracker = VerificationTracker(
        make_policy(EnvelopeQualification.QUALIFIED),
        command_id="cmd-verified", action=CoolingState.ON, started_s=0.0,
    )
    electrical = tracker.observe(VerificationObservation(
        now_s=0.5, current_a=8.0, current_quality=QualityState.VALID,
        power_w=80.0, power_quality=QualityState.VALID,
        thermal_t_representative_c=30.0, thermal_quality=QualityState.VALID,
        applied_cooling=CoolingState.ON,
    ))
    assert electrical.state is VerificationState.ELECTRICAL_VERIFIED
    snap = tracker.observe(VerificationObservation(
        now_s=2.0, thermal_t_representative_c=28.5,
        thermal_quality=QualityState.VALID, applied_cooling=CoolingState.ON,
    ))
    assert snap.state is VerificationState.VERIFIED
    assert snap.health is CoolingHealthState.HEALTHY_RESPONSE


def test_bare_baseline_cannot_verify_thermal_response():
    tracker = VerificationTracker(
        make_policy(EnvelopeQualification.QUALIFIED),
        command_id="cmd-bare-baseline", action=CoolingState.ON, started_s=0.0,
        baseline_temperature_c=30.0,
    )
    tracker.observe(VerificationObservation(
        now_s=0.5, current_a=8.0, current_quality=QualityState.VALID,
        power_w=80.0, power_quality=QualityState.VALID,
        applied_cooling=CoolingState.ON,
    ))
    snap = tracker.observe(VerificationObservation(
        now_s=1.0, thermal_t_representative_c=28.5,
        thermal_quality=QualityState.VALID, applied_cooling=CoolingState.ON,
    ))
    assert snap.state is VerificationState.ELECTRICAL_VERIFIED
    assert not snap.thermal_response_observed
    assert tracker.tick(5.6).state is VerificationState.UNKNOWN


def test_electrical_failure_requires_applied_and_fresh_coverage():
    policy = replace(
        make_policy(EnvelopeQualification.QUALIFIED),
        electrical_evidence_max_age_s=0.25,
    )
    tracker = VerificationTracker(
        policy, command_id="cmd-elec-fail", action=CoolingState.ON,
        started_s=0.0,
    )
    tracker.observe(VerificationObservation(
        now_s=1.9, current_a=1.0, current_quality=QualityState.VALID,
        applied_cooling=CoolingState.ON,
    ))
    snap = tracker.tick(2.1)
    assert snap.state is VerificationState.FAILED_ELECTRICAL
    assert snap.health is CoolingHealthState.ELECTRICAL_RESPONSE_MISSING


def test_thermal_failure_requires_fresh_followup():
    policy = replace(
        make_policy(EnvelopeQualification.QUALIFIED),
        thermal_evidence_max_age_s=0.25,
    )
    tracker = VerificationTracker(
        policy, command_id="cmd-thermal-fail", action=CoolingState.ON,
        started_s=0.0,
    )
    tracker.observe(VerificationObservation(
        now_s=0.5, current_a=8.0, current_quality=QualityState.VALID,
        power_w=80.0, power_quality=QualityState.VALID,
        thermal_t_representative_c=30.0, thermal_quality=QualityState.VALID,
        applied_cooling=CoolingState.ON,
    ))
    tracker.observe(VerificationObservation(
        now_s=5.4, thermal_t_representative_c=29.8,
        thermal_quality=QualityState.VALID, applied_cooling=CoolingState.ON,
    ))
    snap = tracker.tick(5.6)
    assert snap.state is VerificationState.FAILED_THERMAL
    assert snap.health is CoolingHealthState.THERMAL_EFFECTIVENESS_DEGRADED


def test_off_current_anomaly_requires_applied_off_feedback():
    tracker = VerificationTracker(
        make_policy(EnvelopeQualification.QUALIFIED),
        command_id="cmd-off-no-feedback", action=CoolingState.OFF,
        started_s=0.0,
    )
    tracker.observe(VerificationObservation(
        now_s=0.5, current_a=1.0, current_quality=QualityState.VALID,
    ))
    assert tracker.tick(2.1).state is VerificationState.UNKNOWN

    confirmed = VerificationTracker(
        make_policy(EnvelopeQualification.QUALIFIED),
        command_id="cmd-off-confirmed", action=CoolingState.OFF,
        started_s=0.0,
    )
    snap = confirmed.observe(VerificationObservation(
        now_s=0.5, current_a=1.0, current_quality=QualityState.VALID,
        applied_cooling=CoolingState.OFF,
    ))
    assert snap.state is VerificationState.FAILED_ELECTRICAL
    assert snap.health is CoolingHealthState.CONTROL_ELECTRICAL_ANOMALY


def test_qualified_envelope_requires_power_bounds():
    with pytest.raises(ConfigError, match="power bounds"):
        replace(make_policy(), qualification=EnvelopeQualification.QUALIFIED)


def test_off_confirmation_requires_fresh_applied_feedback():
    policy = replace(
        make_policy(EnvelopeQualification.QUALIFIED),
        electrical_evidence_max_age_s=0.25,
    )
    tracker = VerificationTracker(
        policy, command_id="cmd-off-fresh", action=CoolingState.OFF,
        started_s=0.0,
    )
    tracker.observe(VerificationObservation(
        now_s=1.9, current_a=0.0, current_quality=QualityState.VALID,
        applied_cooling=CoolingState.OFF,
    ))
    assert tracker.tick(2.1).state is VerificationState.NOT_REQUIRED
