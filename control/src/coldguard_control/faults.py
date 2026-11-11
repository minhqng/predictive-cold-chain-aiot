"""Safe fault-injection protocol and fault oracle (Member D, W10).

Scope (Doc 05D section 42): define fault tests that prove the *mechanism*
without damaging hardware. This module is pure: it names injection classes,
techniques, preconditions, expected policy behavior and evidence. It never
performs an injection and never claims a physical run happened.

Authority:

- injection hierarchy and avoid-list: Doc 03 section 104 (software/state
  injection first; avoid short circuits, overheating, mains manipulation,
  destructive fan blocking, fuse bypass);
- explicit unsafe-injections blacklist: Doc 05D D-W10-04;
- S4 electrical-response-missing: Doc 03 sections 103 DIAG-02, 66 ACC-PHY-06
  ("issue ON while intentionally preventing legal execution in a safe test
  mode" -> no electrical response, health != HEALTHY_RESPONSE);
- sensor degraded: Doc 03 section 104 hierarchy level 3 (safe low-voltage
  disconnect), Doc 01 section 19 DEGRADED semantics;
- PZEM unavailable: Doc 03 section 104 hierarchy level 2 (communication-layer
  removal), Doc 01 section 28 F-ELEC-01;
- fault oracle (D-W10-05): for each fault, expected state, expected policy,
  expected event, expected physical effect.

No-root-cause rule: Doc 01 section 22.3 forbids calling "ON current missing"
"TEC_BROKEN" immediately; candidate causes are enumerated, and no protocol or
oracle row in this module claims a component root cause.

Nothing here is executable evidence. A protocol with status ``OPEN`` is a
design definition; running it requires the physical preconditions listed on
the protocol, owner approval, and committed capture evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InjectionClass(str, Enum):
    """Preferred injection hierarchy (Doc 03 section 104, most to least
    preferred)."""

    SOFTWARE_STATE = "SOFTWARE_STATE"
    NETWORK_ISOLATION = "NETWORK_ISOLATION"
    SAFE_LOW_VOLTAGE_DISCONNECT = "SAFE_LOW_VOLTAGE_DISCONNECT"
    COMMUNICATION_REMOVAL = "COMMUNICATION_REMOVAL"
    CONTROLLED_NON_DESTRUCTIVE = "CONTROLLED_NON_DESTRUCTIVE"


class FaultProtocolStatus(str, Enum):
    """Whether a protocol may be executed.

    ``DEFINED``: protocol and oracle are designed; execution still requires
    the listed physical preconditions. ``OPEN``: design only, a named gap must
    close before the protocol may even be attempted.
    """

    DEFINED = "DEFINED"
    OPEN = "OPEN"


class UnsafeInjectionError(ValueError):
    """The requested technique is on the forbidden list or not in the
    protocol's allowed technique set."""


class TechniqueNotAllowedError(ValueError):
    """The technique is not part of this protocol's allowed technique set."""


@dataclass(frozen=True, slots=True)
class UnsafeInjection:
    """One explicitly forbidden injection (Doc 05D D-W10-04).

    These are named so a protocol can never accidentally use them and so a
    review can check each one is absent from every protocol.
    """

    technique_id: str
    name: str
    why_forbidden: str
    source: str


_FORBIDDEN_INJECTIONS: tuple[UnsafeInjection, ...] = (
    UnsafeInjection(
        technique_id="FORBIDDEN-SHORT-CIRCUIT",
        name="Short circuit",
        why_forbidden=(
            "Destructive energization; can damage the TEC branch, driver, "
            "fuse and terminals and creates an uncontrolled current path "
            "(Doc 03 section 104 avoid-list, Doc 05D D-W10-04)."
        ),
        source="Doc 03 section 104; Doc 05D D-W10-04",
    ),
    UnsafeInjection(
        technique_id="FORBIDDEN-FUSE-BYPASS",
        name="Fuse bypass",
        why_forbidden=(
            "Removes the overcurrent protection the electrical design relies "
            "on; any later fault becomes unbounded (Doc 03 section 104 "
            "avoid-list, Doc 05D D-W10-04)."
        ),
        source="Doc 03 section 104; Doc 05D D-W10-04",
    ),
    UnsafeInjection(
        technique_id="FORBIDDEN-DESTRUCTIVE-THERMAL-OVERLOAD",
        name="Destructive thermal overload",
        why_forbidden=(
            "Deliberate overheating drives the hot side beyond its "
            "characterized envelope; it damages the TEC/heat-sink and is not "
            "reversible (Doc 03 section 104 'overheating', Doc 05D "
            "D-W10-04)."
        ),
        source="Doc 03 section 104; Doc 05D D-W10-04",
    ),
    UnsafeInjection(
        technique_id="FORBIDDEN-UNSAFE-MAINS-WORK",
        name="Unsafe mains work",
        why_forbidden=(
            "Mains manipulation is a personal-safety hazard and is outside "
            "the project's low-voltage test authority (Doc 03 section 104 "
            "'mains manipulation', Doc 05D D-W10-04)."
        ),
        source="Doc 03 section 104; Doc 05D D-W10-04",
    ),
    UnsafeInjection(
        technique_id="FORBIDDEN-LONG-HOT-SIDE-FAN-STALL",
        name="Intentional long hot-side fan stall",
        why_forbidden=(
            "Prolonged hot-side fan stall with the TEC energized is an "
            "intentional thermal overload of the rejection path; it risks "
            "the TEC junction and surrounding hardware (Doc 05D D-W10-04)."
        ),
        source="Doc 05D D-W10-04",
    ),
)

FORBIDDEN_TECHNIQUE_IDS: frozenset[str] = frozenset(
    item.technique_id for item in _FORBIDDEN_INJECTIONS
)


def all_unsafe_injections() -> tuple[UnsafeInjection, ...]:
    """The full explicit blacklist (Doc 05D D-W10-04)."""
    return _FORBIDDEN_INJECTIONS


@dataclass(frozen=True, slots=True)
class InjectionTechnique:
    """One allowed, safe injection technique.

    ``injection_class`` places it in the Doc 03 section 104 hierarchy;
    ``actuation_prevented`` records whether the technique structurally
    prevents physical actuation (the preferred property per D-W10-01).
    """

    technique_id: str
    name: str
    injection_class: InjectionClass
    actuation_prevented: bool
    method: str
    source: str


_ALLOWED_TECHNIQUES: dict[str, InjectionTechnique] = {
    technique.technique_id: technique
    for technique in (
        InjectionTechnique(
            technique_id="SW-NO-ACTUATION-MODE",
            name="Software/test mode prevents actuation",
            injection_class=InjectionClass.SOFTWARE_STATE,
            actuation_prevented=True,
            method=(
                "A software/test mode keeps the command path fully visible "
                "(command created, validated, published, ACKed) while the "
                "output stage is structurally prevented from energizing. "
                "Expected: command recorded, no electrical response, health "
                "!= HEALTHY_RESPONSE (Doc 03 section 66 ACC-PHY-06)."
            ),
            source="Doc 05D D-W10-01; Doc 03 sections 103 DIAG-02, 66",
        ),
        InjectionTechnique(
            technique_id="SW-SENSOR-ROLE-INVALID",
            name="Test-only single sensor-role invalidation",
            injection_class=InjectionClass.SOFTWARE_STATE,
            actuation_prevented=False,
            method=(
                "Use the compile-time-gated, test-only firmware hook to make "
                "one named DS18B20 role unavailable while retaining the ROM "
                "map and recording degradation plus recovery. The hook is "
                "disabled in production builds."
            ),
            source="A-W21-02 on-device evidence; Doc 03 section 104 hierarchy level 1",
        ),
        InjectionTechnique(
            technique_id="SW-PZEM-TRANSPORT-DISABLE",
            name="Test-only PZEM transport-boundary disable",
            injection_class=InjectionClass.SOFTWARE_STATE,
            actuation_prevented=False,
            method=(
                "Use the compile-time-gated, test-only firmware hook at the "
                "RS-485 transport boundary so PZEM values become unavailable "
                "without touching mains or actuator wiring, then record recovery."
            ),
            source="A-W21-03 on-device evidence; Doc 03 section 104 hierarchy level 1",
        ),
        InjectionTechnique(
            technique_id="SENSOR-SAFE-DISCONNECT",
            name="Safe low-voltage sensor disconnect",
            injection_class=InjectionClass.SAFE_LOW_VOLTAGE_DISCONNECT,
            actuation_prevented=False,
            method=(
                "Disconnect a redundant/low-voltage sensor channel so its "
                "quality becomes DEGRADED/UNKNOWN while the representative "
                "thermal channel remains valid. No mains or actuator power "
                "is touched (Doc 03 section 104 hierarchy level 3)."
            ),
            source="Doc 05D D-W10-02; Doc 03 section 104",
        ),
        InjectionTechnique(
            technique_id="PZEM-COMM-REMOVAL",
            name="PZEM communication-layer removal",
            injection_class=InjectionClass.COMMUNICATION_REMOVAL,
            actuation_prevented=False,
            method=(
                "Remove PZEM communication (bus/disconnect at the "
                "communication layer) so the electrical channel becomes "
                "unavailable; the actuator is never touched, and thermal "
                "safety continues on the thermal channel (Doc 01 section 28 "
                "F-ELEC-01)."
            ),
            source="Doc 05D D-W10-03; Doc 01 section 28 F-ELEC-01",
        ),
        InjectionTechnique(
            technique_id="BROKER-ISOLATION",
            name="Broker network isolation",
            injection_class=InjectionClass.NETWORK_ISOLATION,
            actuation_prevented=False,
            method=(
                "Isolate the broker while the device runs; local control "
                "continues and SAFE_LOCAL semantics apply. Pure network "
                "action, no hardware disturbance (Doc 03 section 104 "
                "hierarchy level 2, section 105 RES-01)."
            ),
            source="Doc 03 sections 104, 105 RES-01",
        ),
    )
}


def all_allowed_techniques() -> tuple[InjectionTechnique, ...]:
    """Stable ordered list of allowed techniques."""
    return tuple(
        _ALLOWED_TECHNIQUES[key] for key in sorted(_ALLOWED_TECHNIQUES)
    )


def get_technique(technique_id: str) -> InjectionTechnique:
    try:
        return _ALLOWED_TECHNIQUES[technique_id]
    except KeyError as exc:
        raise TechniqueNotAllowedError(
            f"{technique_id!r} is not an allowed injection technique; "
            "allowed: " + ", ".join(sorted(_ALLOWED_TECHNIQUES))
        ) from exc


@dataclass(frozen=True, slots=True)
class FaultOracleRow:
    """One D-W10-05 oracle row: the four expected outcomes for a fault.

    ``expected_physical_effect`` describes what the *test mode* guarantees
    physically (e.g. no branch energization), not what a broken component
    would do. ``candidate_causes`` may enumerate plausible causes per Doc 01
    section 22.3; ``root_cause_claimed`` must stay ``False`` in this
    protocol layer (root cause is a W11/incident finding, never an oracle
    expectation).
    """

    fault_id: str
    expected_state: str
    expected_policy: str
    expected_event: str
    expected_physical_effect: str
    candidate_causes: tuple[str, ...] = ()
    root_cause_claimed: bool = False


@dataclass(frozen=True, slots=True)
class FaultProtocol:
    """One safe fault-injection protocol (05D D-W10-01..05)."""

    protocol_id: str
    fault_id: str
    title: str
    technique_ids: tuple[str, ...]
    required_preconditions: tuple[str, ...]
    required_evidence: tuple[str, ...]
    actuation_prevented: bool
    oracle: FaultOracleRow
    status: FaultProtocolStatus
    owner: str
    source: str
    notes: str = ""


_PROTOCOLS: dict[str, FaultProtocol] = {
    "S4-ELECTRICAL-RESPONSE-MISSING": FaultProtocol(
        protocol_id="S4-ELECTRICAL-RESPONSE-MISSING",
        fault_id="F-ELEC-04",
        title="S4 electrical-response-missing fault",
        technique_ids=("SW-NO-ACTUATION-MODE",),
        required_preconditions=(
            "safe test mode verified to prevent actuation before any "
            "command is issued",
            "thermal representative channel VALID and fresh",
            "electrical (PZEM) channel available and calibrated",
            "operator authorized and capture tooling ready",
        ),
        required_evidence=(
            "command record (created/validated/published/ACKed)",
            "no electrical response within the configured response window",
            "diagnosis event with reason ELECTRICAL_RESPONSE_MISSING",
            "no physical branch energization observed",
        ),
        actuation_prevented=True,
        oracle=FaultOracleRow(
            fault_id="F-ELEC-04",
            expected_state="ELECTRICAL_RESPONSE_MISSING",
            expected_policy=(
                "fault recorded; actuation HOLD; predictive blocked; no "
                "lockout invented (disposition owned by W11 D-W11-04)"
            ),
            expected_event="reason ELECTRICAL_RESPONSE_MISSING",
            expected_physical_effect=(
                "no branch energization (test mode structurally prevents "
                "it); no damage"
            ),
            candidate_causes=(
                "driver not enabled",
                "fuse/open circuit",
                "wiring",
                "PZEM issue",
                "TEC branch issue",
            ),
            root_cause_claimed=False,
        ),
        status=FaultProtocolStatus.OPEN,
        owner=(
            "A (physical S4 test mode + capture) / D (oracle + diagnosis)"
        ),
        source="Doc 05D D-W10-01/05; Doc 03 sections 103 DIAG-02, 66",
        notes=(
            "Status OPEN until the safe no-actuation test mode exists in "
            "firmware and Member A commits an actual S4 capture. Host-side "
            "fixtures may exercise the oracle logic but are not physical "
            "evidence."
        ),
    ),
    "SENSOR-DEGRADED": FaultProtocol(
        protocol_id="SENSOR-DEGRADED",
        fault_id="F-PHY-01",
        title="Sensor degraded protocol",
        technique_ids=("SW-SENSOR-ROLE-INVALID", "SENSOR-SAFE-DISCONNECT"),
        required_preconditions=(
            "at least one representative thermal channel remains VALID",
            "disconnected channel is low-voltage and safe to disconnect",
            "capture tooling records per-channel quality",
        ),
        required_evidence=(
            "quality of the disconnected channel becomes DEGRADED/UNKNOWN",
            "policy reports degraded sensing and blocks predictive",
            "reactive thermal control continues on the valid channel",
        ),
        actuation_prevented=False,
        oracle=FaultOracleRow(
            fault_id="F-PHY-01",
            expected_state="DEGRADED thermal quality; diagnosis UNKNOWN or "
            "healthy only on the still-valid channels",
            expected_policy=(
                "NORMAL with degraded_sensing; predictive intervention "
                "blocked; local threshold authoritative (Doc 02 section "
                "40.1, Doc 05D D-W10-02)"
            ),
            expected_event="reason SENSOR_DEGRADED",
            expected_physical_effect="none beyond the disconnected channel",
            candidate_causes=("sensor disconnect", "sensor drift"),
            root_cause_claimed=False,
        ),
        status=FaultProtocolStatus.DEFINED,
        owner="A (physical disconnect) / D (policy semantics)",
        source="Doc 05D D-W10-02/05; Doc 01 sections 19, 28 F-PHY-01",
    ),
    "PZEM-UNAVAILABLE": FaultProtocol(
        protocol_id="PZEM-UNAVAILABLE",
        fault_id="F-ELEC-01",
        title="PZEM unavailable protocol",
        technique_ids=("SW-PZEM-TRANSPORT-DISABLE", "PZEM-COMM-REMOVAL"),
        required_preconditions=(
            "PZEM is the only electrical channel; its removal leaves the "
            "actuator and thermal channels untouched",
            "communication-layer removal method confirmed safe (no "
            "terminal work)",
            "capture tooling records electrical quality per poll",
        ),
        required_evidence=(
            "electrical quality becomes UNKNOWN/INVALID",
            "diagnosis is UNKNOWN, never HEALTHY_RESPONSE on absent "
            "electrical evidence",
            "thermal safety continues on the thermal channel",
        ),
        actuation_prevented=False,
        oracle=FaultOracleRow(
            fault_id="F-ELEC-01",
            expected_state="electrical evidence unavailable; diagnosis "
            "UNKNOWN (Doc 01 section 23.5)",
            expected_policy=(
                "degraded electrical verification; thermal protection "
                "preserved; it does not by itself force OFF (Doc 01 section "
                "28 F-ELEC-01, 05D D-W11-04)"
            ),
            expected_event="reason PZEM_UNAVAILABLE",
            expected_physical_effect="none (communication layer only)",
            candidate_causes=("PZEM bus disconnect", "PZEM unit failure"),
            root_cause_claimed=False,
        ),
        status=FaultProtocolStatus.DEFINED,
        owner="A (communication-layer removal) / D (diagnosis semantics)",
        source="Doc 05D D-W10-03/05; Doc 01 section 28 F-ELEC-01",
    ),
}


def all_protocols() -> tuple[FaultProtocol, ...]:
    """Stable ordered fault protocols."""
    return tuple(_PROTOCOLS[key] for key in sorted(_PROTOCOLS))


def get_protocol(protocol_id: str) -> FaultProtocol:
    try:
        return _PROTOCOLS[protocol_id]
    except KeyError as exc:
        raise KeyError(
            f"{protocol_id!r} is not a defined fault protocol; "
            "defined: " + ", ".join(sorted(_PROTOCOLS))
        ) from exc


def get_oracle(fault_id: str) -> FaultOracleRow:
    """Look up the oracle row by Doc 01 section 28 fault id."""
    for protocol in all_protocols():
        if protocol.fault_id == fault_id:
            return protocol.oracle
    raise KeyError(
        f"{fault_id!r} has no fault oracle row in the W10 protocol table"
    )


class InjectionVerdict(str, Enum):
    PROTOCOL_ALLOWED = "PROTOCOL_ALLOWED"
    FORBIDDEN = "FORBIDDEN"
    NOT_IN_PROTOCOL = "NOT_IN_PROTOCOL"
    PROTOCOL_NOT_APPROVED = "PROTOCOL_NOT_APPROVED"


@dataclass(frozen=True, slots=True)
class InjectionCheckResult:
    protocol_id: str
    technique_id: str
    verdict: InjectionVerdict
    detail: str


def check_injection(protocol_id: str, technique_id: str) -> InjectionCheckResult:
    """Pure safety gate for one requested injection.

    Decision order (fail closed):

    1. forbidden blacklist (Doc 05D D-W10-04) - never allowed anywhere;
    2. technique must be in the protocol's allowed set (a protocol may not
       invent new techniques);
    3. the protocol itself must be in a status that permits execution
       attempts (``DEFINED``); ``OPEN`` protocols are design-only.

    This only *classifies* the request; it performs no injection.
    """
    if technique_id in FORBIDDEN_TECHNIQUE_IDS:
        return InjectionCheckResult(
            protocol_id=protocol_id,
            technique_id=technique_id,
            verdict=InjectionVerdict.FORBIDDEN,
            detail=(
                "technique is on the explicit unsafe-injections blacklist "
                "(Doc 05D D-W10-04); it may never be executed"
            ),
        )

    try:
        protocol = get_protocol(protocol_id)
    except KeyError:
        return InjectionCheckResult(
            protocol_id=protocol_id,
            technique_id=technique_id,
            verdict=InjectionVerdict.NOT_IN_PROTOCOL,
            detail=f"no such protocol: {protocol_id!r}",
        )

    if technique_id not in protocol.technique_ids:
        return InjectionCheckResult(
            protocol_id=protocol_id,
            technique_id=technique_id,
            verdict=InjectionVerdict.NOT_IN_PROTOCOL,
            detail=(
                "technique is not in this protocol's allowed set "
                f"(allowed: {', '.join(protocol.technique_ids)})"
            ),
        )

    if protocol.status is not FaultProtocolStatus.DEFINED:
        return InjectionCheckResult(
            protocol_id=protocol_id,
            technique_id=technique_id,
            verdict=InjectionVerdict.PROTOCOL_NOT_APPROVED,
            detail=(
                f"protocol status is {protocol.status.value}; a named gap "
                "must close and owner approval recorded before execution"
            ),
        )

    return InjectionCheckResult(
        protocol_id=protocol_id,
        technique_id=technique_id,
        verdict=InjectionVerdict.PROTOCOL_ALLOWED,
        detail=(
            "technique is listed in the protocol; this is not permission to "
            "execute. Physical preconditions and owner approval remain unverified"
        ),
    )


def assert_protocol_allowed(protocol_id: str, technique_id: str) -> InjectionCheckResult:
    """Check protocol membership only; never authorize physical execution."""
    result = check_injection(protocol_id, technique_id)
    if result.verdict is not InjectionVerdict.PROTOCOL_ALLOWED:
        raise UnsafeInjectionError(
            f"{protocol_id} / {technique_id}: "
            f"{result.verdict.value} - {result.detail}"
        )
    return result


def _assert_no_root_cause_claim(protocol: FaultProtocol) -> None:
    """Invariant: no W10 oracle row may claim a component root cause."""
    if protocol.oracle.root_cause_claimed:
        raise AssertionError(
            f"protocol {protocol.protocol_id} oracle claims a root cause; "
            "W10 oracles must not (Doc 01 section 22.3)"
        )
    if "TEC_BROKEN" in protocol.oracle.expected_state:
        raise AssertionError(
            f"protocol {protocol.protocol_id} oracle names a component "
            "failure; only candidate causes may be listed"
        )


def audit_protocols() -> dict[str, tuple[str, ...]]:
    """Self-audit used by tests and evidence: returns protocol id -> list of
    violations (empty tuple means the invariants hold)."""
    violations: dict[str, tuple[str, ...]] = {}
    for protocol in all_protocols():
        problems: list[str] = []
        try:
            _assert_no_root_cause_claim(protocol)
        except AssertionError as exc:
            problems.append(str(exc))
        if not protocol.required_preconditions:
            problems.append("no required preconditions listed")
        if not protocol.required_evidence:
            problems.append("no required evidence listed")
        for technique_id in protocol.technique_ids:
            if technique_id in FORBIDDEN_TECHNIQUE_IDS:
                problems.append(f"uses forbidden technique {technique_id}")
            elif technique_id not in _ALLOWED_TECHNIQUES:
                problems.append(f"unknown technique {technique_id}")
            else:
                technique = _ALLOWED_TECHNIQUES[technique_id]
                if (
                    technique.actuation_prevented
                    and not protocol.actuation_prevented
                ):
                    problems.append(
                        f"technique {technique_id} prevents actuation but "
                        "protocol does not record it"
                    )
        violations[protocol.protocol_id] = tuple(problems)
    return violations
