import pytest
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


def test_tick_does_not_replay_old_electrical_sample():
    tracker = VerificationTracker(
        make_policy(EnvelopeQualification.QUALIFIED),
        command_id="cmd-tick", action=CoolingState.ON, started_s=0.0,
    )
    tracker.observe(VerificationObservation(
        now_s=0.5, current_a=1.0, current_quality=QualityState.VALID,
    ))
    snap = tracker.tick(3.0)
    assert snap.state is VerificationState.FAILED_ELECTRICAL
    assert not snap.electrical_response_observed


def test_unqualified_failure_stays_unknown():
    tracker = VerificationTracker(
        make_policy(), command_id="cmd-candidate", action=CoolingState.ON,
        started_s=0.0,
    )
    tracker.observe(VerificationObservation(
        now_s=0.5, current_a=1.0, current_quality=QualityState.VALID,
    ))
    snap = tracker.tick(3.0)
    assert snap.state is VerificationState.UNKNOWN
    assert snap.health is CoolingHealthState.UNKNOWN
