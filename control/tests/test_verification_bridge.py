import pytest

from coldguard_control import CoolingHealthState, EnvelopeQualification
from coldguard_control.verification_bridge import (
    A_LIFECYCLE_ORDER,
    AObservationalLifecycle,
    assess_a_lifecycle_for_d,
)


def lifecycle(**overrides):
    values = {
        "command_id": "cmd-1",
        "stages": A_LIFECYCLE_ORDER,
        "usable_for_health_claim": False,
        "firmware_executed": False,
        "source": "synthetic fixture",
    }
    values.update(overrides)
    return AObservationalLifecycle(**values)


def test_full_a_fixture_chain_does_not_become_d_health_claim():
    result = assess_a_lifecycle_for_d(
        lifecycle(), EnvelopeQualification.CANDIDATE_UNQUALIFIED
    )
    assert result.observational_chain_complete is True
    assert result.direct_health_promotion_allowed is False
    assert result.d_health_state is CoolingHealthState.UNKNOWN
    assert result.reason == "FIXTURE_OR_HOST_TRACE_NOT_PHYSICAL"


def test_qualified_physical_chain_is_only_tracker_input():
    result = assess_a_lifecycle_for_d(
        lifecycle(
            firmware_executed=True,
            usable_for_health_claim=True,
            source="qualified physical capture",
        ),
        EnvelopeQualification.QUALIFIED,
    )
    assert result.eligible_for_d_tracker_input is True
    assert result.direct_health_promotion_allowed is False
    assert result.d_health_state is CoolingHealthState.UNKNOWN
    assert result.reason == "ELIGIBLE_AS_TRACKER_INPUT_NOT_A_HEALTH_VERDICT"


def test_unqualified_envelope_blocks_tracker_input():
    result = assess_a_lifecycle_for_d(
        lifecycle(firmware_executed=True, usable_for_health_claim=True),
        EnvelopeQualification.CANDIDATE_UNQUALIFIED,
    )
    assert result.eligible_for_d_tracker_input is False
    assert result.reason == "D_ENVELOPE_NOT_QUALIFIED"


def test_stages_must_be_ordered_and_known():
    with pytest.raises(ValueError, match="ordered"):
        lifecycle(stages=("DEVICE_ACK", "COMMAND_SEEN"))
    with pytest.raises(ValueError, match="unknown"):
        lifecycle(stages=("COMMAND_SEEN", "HEALTHY_RESPONSE"))
