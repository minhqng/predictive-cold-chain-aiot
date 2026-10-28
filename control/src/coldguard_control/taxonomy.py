"""Failure taxonomy for the W03 policy core (05D D-W03-03).

Doc 05D asks whether each Doc 01 physical failure should be *ignored,
degraded, fallen back from, or locked out*. Docs 00-02 never authorize silent
ignoring of a listed physical failure, so the enum deliberately has no
``IGNORE`` member: a failure always has an explicit, auditable handling.

``NOT_CONTRACTED`` is a first-class outcome, not a failure to finish the
mapping. It records that the observation exists in Doc 01 but the *control
disposition* (escalation timing, forced-OFF rule, lockout condition) is owned
by a later week and is not yet approved. Callers must not treat such a rule as
a frozen policy decision.

Owner references are to Doc 04 / Doc 05D work packages, not to people.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import FailureDisposition, ReasonCode


class UnknownFailureError(KeyError):
    """The failure id is not part of the Doc 01 section 28 taxonomy."""


@dataclass(frozen=True, slots=True)
class FailureRule:
    """One taxonomy row.

    ``disposition`` is the *default* handling under the documented design.
    ``escalation`` states the documented condition under which handling becomes
    stricter; policy.py applies the physical-state consequences (for example
    all thermal channels invalid -> ``FAULT_LOCKOUT``).
    """

    failure_id: str
    title: str
    disposition: FailureDisposition
    reason_code: ReasonCode | None
    owner: str
    contract_status: str
    escalation: str
    source: str


_RULES: dict[str, FailureRule] = {
    "F-PHY-01": FailureRule(
        failure_id="F-PHY-01",
        title="Sensor missing",
        disposition=FailureDisposition.DEGRADE,
        reason_code=ReasonCode.SENSOR_DEGRADED,
        owner="A (sensor validity) / D (degraded policy)",
        contract_status="PARTIAL",
        escalation=(
            "If no valid representative channel remains, the thermal state "
            "becomes INVALID/UNKNOWN and policy.py returns FAULT_LOCKOUT "
            "(Doc 01 section 19.4, Doc 02 section 2.7)."
        ),
        source="Doc 01 sections 19, 28 F-PHY-01; Doc 02 section 40.1",
    ),
    "F-PHY-02": FailureRule(
        failure_id="F-PHY-02",
        title="Sensor invalid / CRC / read error",
        disposition=FailureDisposition.DEGRADE,
        reason_code=ReasonCode.SENSOR_INVALID,
        owner="A (sensor validity) / D (degraded policy)",
        contract_status="PARTIAL",
        escalation=(
            "An invalid value is never substituted (PHY-DS-004). If the "
            "representative source is unusable, policy.py locks out rather "
            "than acting on a guess."
        ),
        source="Doc 01 sections 19, 28 F-PHY-02; PHY-DS-004",
    ),
    "F-PHY-03": FailureRule(
        failure_id="F-PHY-03",
        title="Sensor position / configuration drift",
        disposition=FailureDisposition.NOT_CONTRACTED,
        reason_code=None,
        owner="A (installation validity) / W11 (diagnosis)",
        contract_status="NOT_CONTRACTED",
        escalation=(
            "No runtime position/geometry validity check or data-invalidation "
            "rule is frozen in Docs 00-05D. Must not be silently ignored; "
            "Member A must define detectable evidence before a policy rule is "
            "attached."
        ),
        source="Doc 01 section 28 F-PHY-03; Doc 05D D-W11-04",
    ),
    "F-PHY-04": FailureRule(
        failure_id="F-PHY-04",
        title="Door signal unavailable",
        disposition=FailureDisposition.DEGRADE,
        reason_code=ReasonCode.DOOR_DISTURBANCE,
        owner="B (features) / C (telemetry) / D (policy)",
        contract_status="PARTIAL",
        escalation=(
            "Predictive door-context features are unavailable, so predictive "
            "intervention is blocked; local thermal protection continues "
            "unchanged. Door signal is not a P0 safety interlock."
        ),
        source="Doc 01 sections 17.7, 28 F-PHY-04; Doc 02 section 40.1",
    ),
    "F-ELEC-01": FailureRule(
        failure_id="F-ELEC-01",
        title="PZEM communication unavailable",
        disposition=FailureDisposition.DEGRADE,
        reason_code=ReasonCode.PZEM_UNAVAILABLE,
        owner="A (hardware truth) / W11 (diagnosis)",
        contract_status="PARTIAL",
        escalation=(
            "Electrical verification and electrical fault detection are "
            "degraded; thermal safety is preserved where possible "
            "(Doc 05D section 47). It does not by itself force OFF."
        ),
        source="Doc 01 section 28 F-ELEC-01; Doc 05D D-W11-04",
    ),
    "F-ELEC-02": FailureRule(
        failure_id="F-ELEC-02",
        title="Wrong PZEM range / profile",
        disposition=FailureDisposition.DEGRADE,
        reason_code=ReasonCode.PZEM_CONFIG_INVALID,
        owner="A (calibration/config) / C (ingestion validity)",
        contract_status="PARTIAL",
        escalation=(
            "Measurements are semantically invalid and must not be used as "
            "electrical evidence; the PZEM channel is treated as unavailable "
            "until configuration is corrected."
        ),
        source="Doc 01 sections 28 F-ELEC-02, 33",
    ),
    "F-ELEC-03": FailureRule(
        failure_id="F-ELEC-03",
        title="Unexpected OFF current",
        disposition=FailureDisposition.LOCKOUT,
        reason_code=ReasonCode.CONTROL_ELECTRICAL_ANOMALY,
        owner="A (measurement) / D (lockout policy) / W11",
        contract_status="CONTRACTED",
        escalation=(
            "High severity. Actuation cannot be guaranteed safe; "
            "policy.py maps this to FAULT_LOCKOUT "
            "(Doc 02 section 2.7, Doc 05D D-W11-03)."
        ),
        source="Doc 01 sections 22.4, 28 F-ELEC-03; Doc 02 section 2.7",
    ),
    "F-ELEC-04": FailureRule(
        failure_id="F-ELEC-04",
        title="ON current missing",
        disposition=FailureDisposition.NOT_CONTRACTED,
        reason_code=ReasonCode.ELECTRICAL_RESPONSE_MISSING,
        owner="W11 D-W11-01 / D-W11-04",
        contract_status="NOT_CONTRACTED",
        escalation=(
            "The observation is required, but whether/when it forces OFF or "
            "enters lockout is explicitly left to W11 D-W11-04. W03 must not "
            "invent that escalation."
        ),
        source="Doc 01 section 28 F-ELEC-04; Doc 05D D-W11-01/04",
    ),
    "F-ELEC-05": FailureRule(
        failure_id="F-ELEC-05",
        title="Supply / terminal abnormality",
        disposition=FailureDisposition.LOCKOUT,
        reason_code=None,
        owner="A (hardware characterization) / W11",
        contract_status="PARTIAL",
        escalation=(
            "Treated as a hardware safety condition (Doc 02 section 2.7): no "
            "escalation on an unsafe supply/terminal condition. The exact "
            "characterized stop condition and detector remain with A/W11."
        ),
        source="Doc 01 section 28 F-ELEC-05; Doc 02 section 2.7",
    ),
    "F-THERM-01": FailureRule(
        failure_id="F-THERM-01",
        title="Weak cooling (thermal response degraded)",
        disposition=FailureDisposition.DEGRADE,
        reason_code=ReasonCode.THERMAL_EFFECTIVENESS_DEGRADED,
        owner="W11 D-W11-02/D-W11-04; A (evidence window)",
        contract_status="PARTIAL",
        escalation=(
            "Predictive action is blocked and the local threshold remains "
            "authoritative. Forced-OFF/lockout is a W11 decision; until then "
            "no extra actuation is invented."
        ),
        source="Doc 01 section 28 F-THERM-01; Doc 05D D-W11-02/04",
    ),
    "F-THERM-02": FailureRule(
        failure_id="F-THERM-02",
        title="Hot-side rejection limitation",
        disposition=FailureDisposition.NOT_CONTRACTED,
        reason_code=None,
        owner="A (thermal characterization) / W11",
        contract_status="NOT_CONTRACTED",
        escalation=(
            "A characterized stop condition does not yet exist "
            "(Doc 01 section 39 envelope is not frozen). Until it does, this "
            "cannot be turned into an automatic lockout rule; presence of an "
            "asserted hardware stop is handled by "
            "PolicyInput.hardware_safety_condition."
        ),
        source="Doc 01 sections 28 F-THERM-02, 39; Doc 05D D-W11-04",
    ),
    "F-THERM-03": FailureRule(
        failure_id="F-THERM-03",
        title="Excessive spatial gradient",
        disposition=FailureDisposition.NOT_CONTRACTED,
        reason_code=None,
        owner="A (validity) / B (features) / W11",
        contract_status="NOT_CONTRACTED",
        escalation=(
            "No approved gradient validity bound exists; acting on an "
            "invented bound would violate the no-magic-constants rule. Data "
            "must not be silently declared valid either."
        ),
        source="Doc 01 sections 28 F-THERM-03, 39.3; Doc 02 section 24.4",
    ),
    "F-NET-01": FailureRule(
        failure_id="F-NET-01",
        title="Backend / broker unavailable",
        disposition=FailureDisposition.FALLBACK,
        reason_code=ReasonCode.NETWORK_UNAVAILABLE,
        owner="D (SAFE_LOCAL policy) / A (local control)",
        contract_status="CONTRACTED",
        escalation=(
            "policy.py enters SAFE_LOCAL after the configured grace and keeps "
            "deterministic local protection; reconnect alone does not restore "
            "remote trust (Doc 02 sections 37-38, 05D section 19)."
        ),
        source="Doc 01 section 28 F-NET-01; Doc 02 sections 37-38",
    ),
    "F-AI-01": FailureRule(
        failure_id="F-AI-01",
        title="Inference unavailable / invalid",
        disposition=FailureDisposition.FALLBACK,
        reason_code=ReasonCode.AI_UNAVAILABLE,
        owner="D (fallback policy) / B (model health)",
        contract_status="CONTRACTED",
        escalation=(
            "Controller A/local deterministic policy remains authoritative. "
            "INVALID state cannot trigger predictive action and one old score "
            "is never reused (SW-SAFE-004, Doc 02 sections 41, 94)."
        ),
        source="Doc 01 section 28 F-AI-01; Doc 02 sections 21, 41",
    ),
}


def classify_failure(failure_id: str) -> FailureRule:
    """Return the documented W03 disposition for one Doc 01 failure id."""
    try:
        return _RULES[failure_id]
    except KeyError as exc:
        raise UnknownFailureError(
            f"{failure_id!r} is not a Doc 01 section 28 failure id"
        ) from exc


def all_failure_rules() -> tuple[FailureRule, ...]:
    """Stable, ordered taxonomy rows for docs/tests."""
    return tuple(_RULES[key] for key in sorted(_RULES))


def failures_with_disposition(
    disposition: FailureDisposition,
) -> tuple[FailureRule, ...]:
    return tuple(
        rule
        for rule in all_failure_rules()
        if rule.disposition is disposition
    )
