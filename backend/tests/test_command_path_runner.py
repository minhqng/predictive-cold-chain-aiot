"""Exercises the owner command-path runner against real member contracts.

Every test drives Member D's real policy/decision-matrix code, Member C's real
``Command`` envelope, the owner bridge, Member A's committed W06 fixture
records and Member A's real ``cg_command_trace`` lifecycle promotion. Nothing
here touches a live broker, a serial port, or a compiled firmware image.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from coldguard_backend.ack_translation import AckTranslationError
from coldguard_backend.command_path_runner import (
    CommandPathError,
    FixtureAckDevice,
    applied_frame_template,
    run_command_path,
    synthetic_applied_frame,
)
from coldguard_backend.command_translation import CommandTranslationError

from coldguard_control.commands import AckStatus, LocalSafetyEvidence
from coldguard_control.config import PolicyConfig
from coldguard_control.policy import (
    PolicyInput,
    PredictionView,
    RemotePathView,
    ThermalView,
)
from coldguard_control.types import (
    CoolingState,
    DeviceMode,
    ModelHealth,
    PolicyState,
    QualityState,
)

FIXTURES = json.loads(
    (pathlib.Path(__file__).resolve().parents[2]
     / "evidence" / "A" / "W06" / "ack-fixture.json").read_text(encoding="utf-8")
)["fixtures"]

COMMAND_ID = "00000000-0000-4000-8000-00000000000b"
ISSUED_AT = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


def _cfg(**overrides) -> PolicyConfig:
    values = dict(
        policy_version="policy-v1",
        representative_source="TMAX",
        upper_on_c=6.5,
        lower_off_c=3.5,
        thermal_max_age_s=120.0,
        command_max_future_skew_s=300.0,
        broker_offline_grace_s=30.0,
        backend_state_max_age_s=60.0,
        safe_local_exit_min_stable_s=60.0,
        predictive_enabled=False,
    )
    values.update(overrides)
    return PolicyConfig(**values)


def _policy_input(**overrides) -> PolicyInput:
    values = dict(
        device_mode=DeviceMode.ONLINE_NORMAL,
        thermal=ThermalView(
            quality=QualityState.VALID, t_representative_c=7.2, age_s=10.0
        ),
        applied_cooling=CoolingState.OFF,
        remote=RemotePathView(
            broker_connected=True,
            broker_offline_s=0.0,
            backend_state_synced=True,
            backend_state_age_s=5.0,
            state_sync_trusted=True,
            remote_command_path_trusted=True,
            network_stable_s=600.0,
            stale_command_pending=False,
        ),
        current_state=PolicyState.NORMAL,
        fan_available=True,
        electrical_quality=QualityState.VALID,
        door_state="CLOSED",
        prediction=None,
    )
    values.update(overrides)
    return PolicyInput(**values)


def _evidence(**overrides) -> LocalSafetyEvidence:
    values = dict(
        device_mode=DeviceMode.ONLINE_NORMAL,
        policy_state=PolicyState.NORMAL,
        thermal_quality=QualityState.VALID,
        thermal_age_s=10.0,
        fan_available=True,
        active_fault=False,
        hardware_safety_condition=False,
    )
    values.update(overrides)
    return LocalSafetyEvidence(**values)


def _preemptive_input() -> PolicyInput:
    """Member D predicts persistent risk above the preemptive threshold.

    ``t_representative_c`` stays inside the hysteresis band so the reactive
    critical band does not pre-empt the predictive evaluation.
    """
    return _policy_input(
        thermal=ThermalView(
            quality=QualityState.VALID, t_representative_c=5.0, age_s=10.0
        ),
        prediction=PredictionView(
            health=ModelHealth.READY,
            model_version="m-v1",
            feature_version="f-v1",
            risk_score=0.9,
            age_s=5.0,
            horizon_s=300.0,
            above_preemptive_s=90.0,
        ),
    )


def _preemptive_cfg() -> PolicyConfig:
    return _cfg(
        predictive_enabled=True,
        watch_threshold=0.6,
        preemptive_threshold=0.8,
        persistence_required_s=60.0,
        prediction_max_age_s=600.0,
    )


def _run(**kwargs):
    """SIMULATION_ONLY: the clock claim is a software fixture (no physical
    synchronized-clock evidence exists in the environment); without the
    claim Member D#90 SAFETY_BLOCKs every dispatch (fail-closed)."""
    options = dict(
        policy_input=_preemptive_input(),
        cfg=_preemptive_cfg(),
        evidence=_evidence(),
        clock_synchronized=True,
        command_id=COMMAND_ID,
        device_id="coldguard-001",
        issued_at=ISSUED_AT,
    )
    options.update(kwargs)
    return run_command_path(**options)


def _applied_frames(boundary: FixtureAckDevice) -> list[str]:
    """Three attributed post-ACK frames: applied, current drawn, chamber falls."""
    template = applied_frame_template()
    boot_id = boundary._fields["boot_id"]
    base_uptime = int(boundary._fields["uptime_ms"])
    frames = []
    for step, current_a, t_inside in (
        (1000, "10.5", "7.2"),
        (2000, "10.6", "6.8"),
        (3000, "10.7", "6.7"),
    ):
        frames.append(
            synthetic_applied_frame(
                template,
                boot_id=boot_id,
                uptime_ms=base_uptime + step,
                cooling_applied="ON",
                current_status="OK",
                current_a=current_a,
                t_inside_status="OK",
                t_inside_c=t_inside,
            )
        )
    return frames


def test_preemptive_intent_round_trips_to_accepted_ack_and_blocks_at_applied():
    outcome = _run()
    # Desired: D PREEMPTIVE_COOLING with ON intent (watch/preemptive semantics).
    assert outcome.desired_decision["policy_state"] == "PREEMPTIVE_COOLING"
    assert outcome.desired_decision["actuation_intent"] == "ON"
    assert outcome.desired_decision["controller_id"] == "PREDICTIVE"
    assert outcome.desired_decision["reason_code"] == "PREDICTED_CRITICAL"
    # Accepted: the D matrix passed every check.
    assert outcome.command_verification["status"] == "ACCEPTED"
    assert outcome.command_verification["outcome"] == "COMMAND_ACCEPTED"
    # Dispatched: the owner bridge rendered Member A's device record.
    assert outcome.dispatched_record is not None
    assert "action_cooling=ON" in outcome.dispatched_record
    assert "action_duty_permille=0" in outcome.dispatched_record  # plain ON, no duty
    assert f"command_id={COMMAND_ID}" in outcome.dispatched_record
    # ACK received: correlated Member C CommandAck envelope.
    assert outcome.ack_command_envelope["status"] == "ACCEPTED"
    assert outcome.ack_command_envelope["command_id"] == COMMAND_ID
    assert "ack_time" not in outcome.ack_command_envelope  # never fabricated
    # Observed: no applied-state evidence exists in this exchange, so Member A's
    # trace tool blocks the promotion; the ACK alone is not a physical claim.
    assert outcome.blocked_at == "APPLIED_STATE"
    assert outcome.lifecycle_trace["summary"]["not_applied"] == 1
    assert outcome.outcome_status == "ACK_RECEIVED_BLOCKED_AT_APPLIED_STATE"


def test_full_promotion_to_thermal_verified_with_attributed_applied_frames():
    boundary = FixtureAckDevice("synchronized-accepted")
    outcome = _run(device_boundary=boundary, post_ack_frames=_applied_frames(boundary))
    assert outcome.blocked_at is None
    row = outcome.lifecycle_trace["commands"][0]
    assert row["stages"] == [
        "COMMAND_SEEN", "DEVICE_ACK", "APPLIED_STATE",
        "ELECTRICAL_VERIFIED", "THERMAL_VERIFIED",
    ]
    assert outcome.lifecycle_trace["summary"]["verdict"] == "TRACED"
    assert outcome.outcome_status == "OBSERVED_TRACE_COMPLETE"
    # Synthetic frame provenance is recorded, never presented as physical.
    assert "synthetic" in outcome.post_ack_frame_provenance


def test_device_expired_verdict_blocks_promotion_at_device_ack():
    outcome = _run(device_boundary=FixtureAckDevice("synchronized-expired"))
    assert outcome.ack_command_envelope is not None
    fixture_status = FIXTURES["synchronized-expired"]["fields"]["status"]
    # The device's own verdict passes through unchanged, never re-labeled.
    assert outcome.ack_command_envelope["status"] == fixture_status
    assert fixture_status != "ACCEPTED"
    row = outcome.lifecycle_trace["commands"][0]
    assert row["blocked_at"] == "DEVICE_ACK"
    assert "nothing beyond the acknowledgement is claimed" in row["notes"][-1]


def test_duplicate_command_returns_canonical_without_redispatch():
    outcome = _run(processed={COMMAND_ID: AckStatus.ACCEPTED})
    assert outcome.command_verification["status"] == "DUPLICATE_CANONICAL"
    assert outcome.command_verification["canonical_status"] == "ACCEPTED"
    assert outcome.command_verification["accepted"] is False
    assert outcome.dispatched_record is None


def test_wrong_device_id_is_refused_by_the_decision_matrix():
    outcome = _run(device_id="coldguard-002", expected_device_id="coldguard-001")
    assert outcome.command_verification["status"] == "REJECTED"
    assert outcome.command_verification["detail"].startswith("command targets another device")
    assert outcome.dispatched_record is None


def test_local_safety_interlocks_block_energization():
    outcome = _run(evidence=_evidence(hardware_safety_condition=True))
    assert outcome.command_verification["status"] == "SAFETY_BLOCKED"
    assert outcome.dispatched_record is None
    second = _run(evidence=_evidence(fan_available=None))
    assert second.command_verification["status"] == "SAFETY_BLOCKED"
    assert second.command_verification["detail"].startswith("heat-rejection fan")


def test_watch_state_issues_no_command():
    cfg = _cfg(
        predictive_enabled=True, watch_threshold=0.6,
        preemptive_threshold=0.8, persistence_required_s=60.0,
        prediction_max_age_s=600.0,
    )
    policy_input = _policy_input(
        thermal=ThermalView(
            quality=QualityState.VALID, t_representative_c=5.0, age_s=10.0
        ),
        prediction=PredictionView(
            health=ModelHealth.READY, model_version="m-v1",
            feature_version="f-v1", risk_score=0.7, age_s=5.0,
            horizon_s=300.0, above_preemptive_s=10.0,  # persistence not met
        ),
    )
    outcome = _run(policy_input=policy_input, cfg=cfg)
    assert outcome.desired_decision["policy_state"] == "WATCH"
    assert outcome.desired_decision["actuation_intent"] == "HOLD"
    assert outcome.command_verification["outcome"] == "INTENT_ONLY"
    assert outcome.dispatched_record is None


def test_command_queued_past_ttl_is_expired_by_the_decision_matrix():
    """A command created earlier is judged at the real validation instant."""
    outcome = _run(validated_at=datetime(2026, 11, 10, 12, 3, 0, tzinfo=timezone.utc))
    assert outcome.command_verification["status"] == "EXPIRED"
    assert outcome.command_verification["reason_code"] == "COMMAND_EXPIRED"
    assert outcome.dispatched_record is None
    assert outcome.ack_command_envelope is None


def test_command_created_in_the_far_future_fails_the_skew_check():
    future = datetime(2026, 11, 10, 12, 10, 0, tzinfo=timezone.utc)
    outcome = _run(issued_at=future, validated_at=ISSUED_AT)
    assert outcome.command_verification["status"] == "REJECTED"
    assert outcome.command_verification["detail"].startswith("created_at is implausibly in the future")


def test_naive_issued_at_fails_closed():
    with pytest.raises(CommandPathError, match="NAIVE_TIMESTAMP"):
        _run(issued_at=datetime(2026, 11, 10, 12, 0, 0))


def test_malformed_ack_fails_closed():
    def broken_device(record: str) -> str:
        return "#CG CMDACK not-a-valid-record"
    with pytest.raises(AckTranslationError, match="INVALID_TOKEN"):
        _run(device_boundary=broken_device)


def test_ack_for_another_command_is_refused_not_silently_accepted():
    boundary = FixtureAckDevice("synchronized-accepted")

    def other_command_device(record: str) -> str:
        return boundary(record).replace(COMMAND_ID, "00000000-0000-4000-8000-00000000ffff")

    with pytest.raises(CommandPathError, match="ACK_COMMAND_MISMATCH"):
        _run(device_boundary=other_command_device)


def test_missing_feedback_raises_instead_of_inventing_a_state():
    def silent_device(record: str) -> str:
        raise TimeoutError("device did not answer")

    with pytest.raises(TimeoutError):
        _run(device_boundary=silent_device)


def test_out_of_order_frames_never_promote_a_stage():
    """Pre-ACK (stale-ordered) applied frames carry no attribution evidence."""
    boundary = FixtureAckDevice("synchronized-accepted")
    template = applied_frame_template()
    stale = synthetic_applied_frame(
        template,
        boot_id=boundary._fields["boot_id"],
        uptime_ms=int(boundary._fields["uptime_ms"]) - 5000,
        cooling_applied="ON", current_status="OK", current_a="10.5",
        t_inside_status="OK", t_inside_c="6.0",
    )
    outcome = _run(device_boundary=boundary, post_ack_frames=[stale])
    assert outcome.blocked_at == "APPLIED_STATE"


def test_duplicate_ack_replay_keeps_canonical_verdict_and_reapplied_flag():
    boundary = FixtureAckDevice("duplicate-replay")
    outcome = _run(device_boundary=boundary)
    envelope = outcome.ack_command_envelope
    assert envelope["status"] == "DUPLICATE_CANONICAL"
    assert envelope["canonical_status"] == "ACCEPTED"
    assert envelope["reapplied"] is False
    # Member A's trace flags a replay that applied again as a violation.
    row = outcome.lifecycle_trace["commands"][0]
    assert row["stages"][-1] == "DEVICE_ACK"


def test_unsynchronized_clock_ack_is_preserved_not_worked_around():
    boundary = FixtureAckDevice("shipped-unsynchronized")
    outcome = _run(device_boundary=boundary)
    envelope = outcome.ack_command_envelope
    assert envelope["time_sync_state"] == "UNSYNCHRONIZED"
    assert envelope["expiry_evaluable"] is False
    # No receipt-time TTL workaround: the device verdict and its
    # un-evaluability stay exactly as the fixture reports them.
    assert envelope["status"] == FIXTURES["shipped-unsynchronized"]["fields"]["status"]


def test_device_provenance_is_recorded_with_every_exchange():
    outcome = _run()
    assert outcome.device_provenance["firmware_executed"] is False
    assert outcome.device_provenance["kind"] == "fixture_ack_device"


def test_device_record_translation_guard_still_applies():
    """An over-long reason fails the dispatch, per the device's record limits."""
    from coldguard_backend.command_translation import (
        translate_command_to_device_serial,
    )
    from coldguard_backend.contracts import Command

    oversized = Command(
        schema_version=1, command_id=COMMAND_ID, device_id="coldguard-001",
        created_at=ISSUED_AT, expires_at=ISSUED_AT + timedelta(seconds=120),
        controller_id="PREDICTIVE", policy_version="p1",
        reason_code="R" * 300,
        action={"cooling": "ON", "duty": None},
    )
    with pytest.raises(CommandTranslationError):
        translate_command_to_device_serial(oversized)

def test_unclaimed_clock_safety_blocks_by_default_under_d90():
    """D#90's normative order: the clock gate fires BEFORE every later check."""
    from coldguard_backend.command_path_runner import d90_compatible_evidence
    base_evidence = _evidence()
    claimed = d90_compatible_evidence(base_evidence, clock_synchronized=False)
    # clock_synchronized=None keeps the caller-supplied evidence verbatim:
    # the D#90 contract itself (clock_synchronized=False) decides.
    outcome = _run(evidence=claimed, clock_synchronized=None)
    assert outcome.command_verification["status"] == "SAFETY_BLOCKED"
    assert outcome.command_verification["reason_code"] == "COMMAND_SAFETY_BLOCKED"
    assert "not synchronized" in outcome.command_verification["detail"]
    # The clock gate precedes expiry: no later check is reached.
    assert "expiry" not in outcome.command_verification["checks_passed"]
    assert outcome.dispatched_record is None
