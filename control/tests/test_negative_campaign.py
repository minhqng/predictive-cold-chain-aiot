from dataclasses import FrozenInstanceError

import pytest

from coldguard_control import (
    REQUIRED_OUTCOMES,
    EvidenceAuthority,
    NegativeCampaignCase,
    NegativeCaseEvidence,
    NegativeOutcome,
    assess_negative_campaign,
)


def complete_evidence(authority=EvidenceAuthority.HOST_SIMULATED):
    return [
        NegativeCaseEvidence(
            case,
            authority,
            REQUIRED_OUTCOMES[case],
            evidence_ref=(f"evidence/D/W21/{case.value}.json"
                          if authority is EvidenceAuthority.LIVE_EVIDENCE else None),
            operator_identity=("member-D"
                               if authority is EvidenceAuthority.LIVE_EVIDENCE else None),
        )
        for case in NegativeCampaignCase
    ]


def test_matrix_defines_all_nine_week_21_cases():
    assert len(NegativeCampaignCase) == 9
    assert set(REQUIRED_OUTCOMES) == set(NegativeCampaignCase)


def test_host_matrix_can_pass_without_claiming_live_completion():
    decision = assess_negative_campaign(complete_evidence())
    assert decision.all_cases_pass is True
    assert decision.live_evidence_complete is False
    assert decision.blockers == ("LIVE_EVIDENCE_REQUIRED_FOR_FINAL_CAMPAIGN",)
    assert decision.physical_command_emitted is False


def test_all_live_results_complete_the_evidence_gate():
    decision = assess_negative_campaign(
        complete_evidence(EvidenceAuthority.LIVE_EVIDENCE)
    )
    assert decision.all_cases_pass is True
    assert decision.live_evidence_complete is True
    assert decision.blockers == ()


def test_live_authority_requires_provenance():
    with pytest.raises(ValueError, match="evidence_ref"):
        NegativeCaseEvidence(
            NegativeCampaignCase.RECONNECT,
            EvidenceAuthority.LIVE_EVIDENCE,
            REQUIRED_OUTCOMES[NegativeCampaignCase.RECONNECT],
        )


def test_mixed_authority_does_not_claim_live_completion():
    evidence = complete_evidence(EvidenceAuthority.LIVE_EVIDENCE)
    evidence[0] = NegativeCaseEvidence(
        evidence[0].case,
        EvidenceAuthority.HOST_SIMULATED,
        evidence[0].observed_outcomes,
    )
    decision = assess_negative_campaign(evidence)
    assert decision.all_cases_pass is True
    assert decision.live_evidence_complete is False


@pytest.mark.parametrize("case", list(NegativeCampaignCase))
def test_each_missing_case_is_an_explicit_blocker(case):
    decision = assess_negative_campaign(
        [item for item in complete_evidence() if item.case is not case]
    )
    assert decision.all_cases_pass is False
    assert decision.live_evidence_complete is False
    assert case in decision.missing_cases
    assert f"MISSING_CASE:{case.value}" in decision.blockers


@pytest.mark.parametrize(
    ("case", "outcome"),
    [
        (NegativeCampaignCase.EXPIRED_COMMAND, NegativeOutcome.REJECTED),
        (NegativeCampaignCase.EXPIRED_COMMAND, NegativeOutcome.NO_ACTUATION),
        (NegativeCampaignCase.EXPIRED_COMMAND, NegativeOutcome.AUDIT_EVENT),
        (
            NegativeCampaignCase.DUPLICATE_COMMAND,
            NegativeOutcome.NO_DUPLICATE_PHYSICAL_EFFECT,
        ),
        (NegativeCampaignCase.OUT_OF_RANGE_COMMAND, NegativeOutcome.REJECTED),
        (NegativeCampaignCase.WRONG_DEVICE_COMMAND, NegativeOutcome.REJECTED),
        (
            NegativeCampaignCase.UNAUTHORIZED_BROKER_PUBLISH,
            NegativeOutcome.ACL_DENIED,
        ),
        (
            NegativeCampaignCase.BACKEND_AUTHORIZATION,
            NegativeOutcome.AUTHORIZATION_DENIED,
        ),
        (
            NegativeCampaignCase.BACKEND_AUTHORIZATION,
            NegativeOutcome.NO_ACTUATION,
        ),
        (
            NegativeCampaignCase.NETWORK_BACKEND_OUTAGE,
            NegativeOutcome.SAFE_LOCAL_ENTERED,
        ),
        (
            NegativeCampaignCase.AI_OUTAGE,
            NegativeOutcome.REACTIVE_LOCAL_FALLBACK,
        ),
        (NegativeCampaignCase.RECONNECT, NegativeOutcome.NO_STALE_ACTUATION),
    ],
)
def test_every_required_outcome_is_enforced(case, outcome):
    evidence = complete_evidence()
    index = next(i for i, item in enumerate(evidence) if item.case is case)
    evidence[index] = NegativeCaseEvidence(
        case,
        EvidenceAuthority.HOST_SIMULATED,
        REQUIRED_OUTCOMES[case] - {outcome},
    )
    decision = assess_negative_campaign(evidence)
    assert case in decision.failed_cases
    assert f"MISSING_OUTCOME:{case.value}:{outcome.value}" in decision.blockers


def test_duplicate_case_is_rejected():
    item = complete_evidence()[0]
    with pytest.raises(ValueError, match="duplicate campaign case"):
        assess_negative_campaign([item, item])


def test_types_are_strict_and_evidence_is_immutable():
    with pytest.raises(TypeError, match="Sequence"):
        assess_negative_campaign("not evidence")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="NegativeCaseEvidence"):
        assess_negative_campaign([object()])  # type: ignore[list-item]
    with pytest.raises(TypeError, match="frozenset"):
        NegativeCaseEvidence(  # type: ignore[arg-type]
            NegativeCampaignCase.RECONNECT,
            EvidenceAuthority.HOST_SIMULATED,
            {NegativeOutcome.NO_STALE_ACTUATION},
        )
    evidence = complete_evidence()[0]
    with pytest.raises(FrozenInstanceError):
        evidence.authority = EvidenceAuthority.LIVE_EVIDENCE  # type: ignore[misc]
