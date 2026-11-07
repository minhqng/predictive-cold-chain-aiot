"""D-only lifecycle wiring test; every sample and envelope is synthetic.

This does not cover MQTT, device firmware, a real ACK, physical measurement or
G3. It catches interface drift between Controller A, command validation and
the verification state machine before A/C supply an end-to-end capture.
"""

from _builders import make_command, make_config, make_evidence, make_input, make_thermal
from coldguard_control import (
    AckStatus, ActuationIntent, ControllerA, ControllerAConfig,
    ControllerASample, CoolingHealthState, CoolingState,
    EnvelopeQualification, QualityState, VerificationObservation,
    VerificationPolicy, VerificationTracker,
    validate_command,
)
from coldguard_control.types import VerificationState


def test_synthetic_reactive_command_to_verified_chain():
    policy = make_config()
    controller = ControllerA(ControllerAConfig(policy, 0.0, 0.0, 0.0, "synthetic"))
    decision = controller.step(ControllerASample(
        1010.0, make_input(thermal=make_thermal(t=9.0))
    ))
    assert decision.intent is ActuationIntent.ON
    assert decision.applied_after is CoolingState.OFF

    ack = validate_command(
        make_command(), make_evidence(policy_state=decision.policy.state),
        policy, now_s=1010.0, expected_device_id="cg-test-001", processed={},
    )
    assert ack.status is AckStatus.ACCEPTED
    assert ack.actuation_intent is ActuationIntent.ON

    # The test supplies fabricated applied-state and physical observations.
    # A real device must supply these independently of the accepted ACK.
    envelope = VerificationPolicy(
        policy_version="synthetic", envelope_id="synthetic-qualified-branch",
        qualification=EnvelopeQualification.QUALIFIED,
        active_current_min_a=7.0, active_current_max_a=10.0,
        off_current_max_a=0.1, electrical_window_s=2.0,
        thermal_window_s=5.0, thermal_min_drop_c=1.0,
        active_power_min_w=50.0, active_power_max_w=100.0,
        source="synthetic fixture; no physical qualification",
    )
    tracker = VerificationTracker(
        envelope, command_id="cmd-synthetic-001", action=CoolingState.ON,
        started_s=1010.0,
    )
    electrical = tracker.observe(VerificationObservation(
        now_s=1010.5, current_a=8.0, current_quality=QualityState.VALID,
        power_w=80.0, power_quality=QualityState.VALID,
        thermal_t_representative_c=30.0, thermal_quality=QualityState.VALID,
        applied_cooling=CoolingState.ON,
    ))
    assert electrical.state is VerificationState.ELECTRICAL_VERIFIED
    final = tracker.observe(VerificationObservation(
        now_s=1012.0, thermal_t_representative_c=28.5,
        thermal_quality=QualityState.VALID, applied_cooling=CoolingState.ON,
    ))
    assert final.state is VerificationState.VERIFIED
    assert final.health is CoolingHealthState.HEALTHY_RESPONSE
