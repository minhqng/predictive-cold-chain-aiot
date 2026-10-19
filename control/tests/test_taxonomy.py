"""W03 failure taxonomy coverage (Doc 01 section 28 -> disposition)."""

from __future__ import annotations

import pytest

from coldguard_control import (
    FailureDisposition,
    ReasonCode,
    UnknownFailureError,
    all_failure_rules,
    classify_failure,
    failures_with_disposition,
)

EXPECTED_IDS = {
    "F-PHY-01",
    "F-PHY-02",
    "F-PHY-03",
    "F-PHY-04",
    "F-ELEC-01",
    "F-ELEC-02",
    "F-ELEC-03",
    "F-ELEC-04",
    "F-ELEC-05",
    "F-THERM-01",
    "F-THERM-02",
    "F-THERM-03",
    "F-NET-01",
    "F-AI-01",
}

EXPECTED_DISPOSITIONS = {
    "F-PHY-01": FailureDisposition.DEGRADE,
    "F-PHY-02": FailureDisposition.DEGRADE,
    "F-PHY-03": FailureDisposition.NOT_CONTRACTED,
    "F-PHY-04": FailureDisposition.DEGRADE,
    "F-ELEC-01": FailureDisposition.DEGRADE,
    "F-ELEC-02": FailureDisposition.DEGRADE,
    "F-ELEC-03": FailureDisposition.LOCKOUT,
    "F-ELEC-04": FailureDisposition.NOT_CONTRACTED,
    "F-ELEC-05": FailureDisposition.LOCKOUT,
    "F-THERM-01": FailureDisposition.DEGRADE,
    "F-THERM-02": FailureDisposition.NOT_CONTRACTED,
    "F-THERM-03": FailureDisposition.NOT_CONTRACTED,
    "F-NET-01": FailureDisposition.FALLBACK,
    "F-AI-01": FailureDisposition.FALLBACK,
}


def test_every_doc01_failure_id_is_mapped() -> None:
    assert {rule.failure_id for rule in all_failure_rules()} == EXPECTED_IDS


@pytest.mark.parametrize(
    ("failure_id", "disposition"),
    sorted(EXPECTED_DISPOSITIONS.items()),
)
def test_documented_disposition(
    failure_id: str, disposition: FailureDisposition
) -> None:
    assert classify_failure(failure_id).disposition is disposition


def test_unknown_failure_id_is_not_silently_accepted() -> None:
    with pytest.raises(UnknownFailureError):
        classify_failure("F-PHY-99")


def test_no_ignore_disposition_exists() -> None:
    assert {member.value for member in FailureDisposition} == {
        "DEGRADE",
        "FALLBACK",
        "LOCKOUT",
        "NOT_CONTRACTED",
    }


def test_uncontracted_rules_are_explicit() -> None:
    assert {
        rule.failure_id
        for rule in failures_with_disposition(
            FailureDisposition.NOT_CONTRACTED
        )
    } == {
        "F-PHY-03",
        "F-ELEC-04",
        "F-THERM-02",
        "F-THERM-03",
    }


def test_lockout_rule_matches_policy_reason_code() -> None:
    assert (
        classify_failure("F-ELEC-03").reason_code
        is ReasonCode.CONTROL_ELECTRICAL_ANOMALY
    )


def test_network_and_ai_failures_fall_back_to_local_policy() -> None:
    assert (
        classify_failure("F-NET-01").disposition
        is FailureDisposition.FALLBACK
    )
    assert (
        classify_failure("F-AI-01").disposition
        is FailureDisposition.FALLBACK
    )


@pytest.mark.parametrize("rule", all_failure_rules(), ids=lambda r: r.failure_id)
def test_every_rule_is_auditable(rule) -> None:
    assert rule.title.strip()
    assert rule.owner.strip()
    assert rule.escalation.strip()
    assert "Doc 01" in rule.source
    assert rule.contract_status in {
        "CONTRACTED",
        "PARTIAL",
        "NOT_CONTRACTED",
    }
    if rule.disposition is FailureDisposition.NOT_CONTRACTED:
        assert rule.contract_status == "NOT_CONTRACTED"
    else:
        assert rule.contract_status != "NOT_CONTRACTED"
