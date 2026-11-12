from dataclasses import FrozenInstanceError

import pytest

from coldguard_control.campaign_integrity import (
    CampaignAssessmentStatus,
    ControllerVariant,
    FrozenControllerIdentity,
    RunEvidence,
    assess_campaign_pair,
    assess_campaign_run,
    compute_config_sha256,
)


DIGEST_A = compute_config_sha256({"controller": "A", "policy": "a-v1"})
DIGEST_B = compute_config_sha256({"controller": "B", "policy": "b-v1"})


def frozen(controller=ControllerVariant.A):
    is_a = controller is ControllerVariant.A
    return FrozenControllerIdentity(
        controller=controller,
        policy_version="a-v1" if is_a else "b-v1",
        config_sha256=DIGEST_A if is_a else DIGEST_B,
        action_profile="reactive-on-off" if is_a else "predictive-on-off",
        failure_policy="fallback-lockout-v1",
    )


def run(controller=ControllerVariant.A, **overrides):
    identity = frozen(controller)
    values = {
        "run_id": "run-a-001" if controller is ControllerVariant.A else "run-b-001",
        "pair_id": "pair-001",
        "controller": controller,
        "policy_version": identity.policy_version,
        "config_sha256": identity.config_sha256,
        "action_profile": identity.action_profile,
        "failure_policy": identity.failure_policy,
        "tuning_changed": False,
        "duplicate_logical_command": False,
        "verification_sensible": True,
        "control_anomaly": False,
    }
    values.update(overrides)
    return RunEvidence(**values)


def test_matching_run_is_accepted_and_preserved_for_pair_ledger():
    evidence = run()
    decision = assess_campaign_run(evidence, frozen())
    assert decision.status is CampaignAssessmentStatus.ACCEPTED
    assert decision.reasons == ()
    assert decision.ledger_record.pair_id == evidence.pair_id
    assert decision.ledger_record.config_sha256 == evidence.config_sha256
    assert decision.silently_corrected is False
    assert decision.physical_command_emitted is False


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"controller": ControllerVariant.B}, "CONTROLLER_IDENTITY_MISMATCH"),
        ({"policy_version": "drifted"}, "POLICY_VERSION_MISMATCH"),
        ({"config_sha256": DIGEST_B}, "CONFIG_SHA256_MISMATCH"),
        ({"action_profile": "changed"}, "ACTION_PROFILE_MISMATCH"),
        ({"failure_policy": "changed"}, "FAILURE_POLICY_MISMATCH"),
        ({"tuning_changed": True}, "ADAPTIVE_TUNING_DETECTED"),
        ({"duplicate_logical_command": True}, "DUPLICATE_LOGICAL_COMMAND_DETECTED"),
        ({"verification_sensible": False}, "NONSENSICAL_VERIFICATION_STATE"),
        ({"control_anomaly": True}, "CONTROL_ANOMALY_DETECTED"),
    ],
)
def test_any_integrity_violation_flags_without_correction(override, reason):
    decision = assess_campaign_run(run(**override), frozen())
    assert decision.status is CampaignAssessmentStatus.FLAGGED
    assert any(item.startswith(reason) for item in decision.reasons)
    assert decision.silently_corrected is False


def test_clean_a_b_pair_is_accepted():
    decision = assess_campaign_pair(
        run(ControllerVariant.A), run(ControllerVariant.B),
        frozen(ControllerVariant.A), frozen(ControllerVariant.B),
    )
    assert decision.pair_status is CampaignAssessmentStatus.ACCEPTED
    assert decision.record.pair_id == "pair-001"
    assert decision.physical_command_emitted is False


def test_pair_identity_mismatch_is_flagged_and_retained():
    decision = assess_campaign_pair(
        run(ControllerVariant.A),
        run(ControllerVariant.B, pair_id="pair-002"),
        frozen(ControllerVariant.A), frozen(ControllerVariant.B),
    )
    assert decision.pair_status is CampaignAssessmentStatus.FLAGGED
    assert any(reason.startswith("PAIR_ID_MISMATCH") for reason in decision.pair_reasons)
    assert decision.record.run_b.pair_id == "pair-002"


def test_records_are_immutable_and_types_are_strict():
    evidence = run()
    with pytest.raises(FrozenInstanceError):
        evidence.policy_version = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError, match="strict boolean"):
        run(tuning_changed=1)
    with pytest.raises(ValueError, match="SHA-256"):
        run(config_sha256="not-a-digest")
