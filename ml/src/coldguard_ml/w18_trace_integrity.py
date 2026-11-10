"""W18 predictive-intervention trace integrity (B-W18-02).

Defines and validates the canonical chain:

    prediction -> warning -> policy decision -> command -> ACK -> physical verify

The validator is read-only.  It never generates, dispatches, retries or
publishes a command, and it never converts an ACK, an applied-state report or a
software fixture into physical evidence.

Canonical anchors: Doc 04 §33 (prediction/policy/command/ACK/electrical/
thermal), Doc 05B §46 B-W18-02, Doc 01 §1.3-1.7 (commanded vs applied vs
electrical vs thermal vs verified action), Doc 03 §1.3 (physical truth outranks
software self-report).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

TRACE_SCHEMA = "coldguard-w18-predictive-intervention-trace-v1"
FIXTURE_EVIDENCE_CLASS = "TEST_ONLY_SYNTHETIC_FIXTURE"
SOFTWARE_EVIDENCE_CLASS = "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
PHYSICAL_FIXTURE_EVIDENCE_CLASS = "SYNTHETIC_TEST_FIXTURE_NOT_PHYSICAL_EVIDENCE"
PHYSICAL_EVIDENCE_CLASSES = frozenset(
    {"MEASURED_PHYSICAL_DATA", "REAL_PHYSICAL_EVIDENCE"}
)
W17_TRACE_SCHEMA = "coldguard-w17-shadow-trace-v1"

TRACE_COMPLETE_SOFTWARE_FIXTURE = "TRACE_COMPLETE_SOFTWARE_FIXTURE"
TRACE_COMPLETE_PENDING_HUMAN_ACCEPTANCE = (
    "TRACE_COMPLETE_PENDING_HUMAN_ACCEPTANCE"
)
TRACE_PARTIAL_MISSING_EVIDENCE = "TRACE_PARTIAL_MISSING_EVIDENCE"
TRACE_INCONSISTENT_IDENTITY = "TRACE_INCONSISTENT_IDENTITY"
TRACE_TEMPORAL_CONTRADICTION = "TRACE_TEMPORAL_CONTRADICTION"
TRACE_PHYSICAL_UNVERIFIED = "TRACE_PHYSICAL_UNVERIFIED"
TRACE_NOT_AUTHORIZED = "TRACE_NOT_AUTHORIZED"
OUTCOMES = (
    TRACE_COMPLETE_SOFTWARE_FIXTURE,
    TRACE_COMPLETE_PENDING_HUMAN_ACCEPTANCE,
    TRACE_PARTIAL_MISSING_EVIDENCE,
    TRACE_INCONSISTENT_IDENTITY,
    TRACE_TEMPORAL_CONTRADICTION,
    TRACE_PHYSICAL_UNVERIFIED,
    TRACE_NOT_AUTHORIZED,
)

STAGE_PREDICTION = "prediction"
STAGE_WARNING = "warning"
STAGE_POLICY = "policy"
STAGE_COMMAND = "command"
STAGE_ACK = "ack"
STAGE_APPLIED = "applied_state"
STAGE_PHYSICAL = "physical_verification"
REQUIRED_STAGES = (
    STAGE_PREDICTION,
    STAGE_WARNING,
    STAGE_POLICY,
    STAGE_COMMAND,
    STAGE_ACK,
    STAGE_APPLIED,
    STAGE_PHYSICAL,
)

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"

POLICY_HYPOTHETICAL = "HYPOTHETICAL"
POLICY_AUTHORIZED = "AUTHORIZED"
POLICY_NOT_EVALUATED = "NOT_EVALUATED"
POLICY_STATUSES = (POLICY_HYPOTHETICAL, POLICY_AUTHORIZED, POLICY_NOT_EVALUATED)

WARNING_STATUSES = (
    "TRIGGERED_SYNTHETIC_ILLUSTRATIVE",
    "NOT_TRIGGERED_SYNTHETIC_ILLUSTRATIVE",
)
ACK_ACCEPTED_STATUSES = frozenset(
    {"ACCEPTED", "ACK_ACCEPTED", "ACCEPTED_TEST_FIXTURE"}
)
ACK_REJECTED_STATUSES = frozenset(
    {"REJECTED", "ACK_REJECTED", "SAFETY_BLOCKED", "EXPIRED"}
)
TERMINAL_COMMAND_SUCCESS = frozenset({"SUCCEEDED", "EXECUTED", "VERIFIED"})
TERMINAL_COMMAND_FAILURE = frozenset(
    {"FAILED", "REJECTED", "EXPIRED", "FAILED_VERIFICATION"}
)
TRUSTED_QUALITY = frozenset(
    {"TRUSTED", "TRUSTED_TEST_FIXTURE", "CALIBRATED", "QUALIFIED"}
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class TraceError(ValueError):
    """The trace envelope is malformed and cannot be assessed."""


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX64.match(value))


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _text(value: Any) -> str:
    return "" if value is None else str(value)


@dataclass(frozen=True)
class InvariantResult:
    invariant_id: str
    requirement: str
    status: str
    observed: str
    reason_code: str | None
    canonical_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "invariant_id": self.invariant_id,
            "requirement": self.requirement,
            "status": self.status,
            "observed": self.observed,
            "reason_code": self.reason_code,
            "canonical_ref": self.canonical_ref,
        }


@dataclass(frozen=True)
class TraceAssessment:
    outcome: str
    trace_id: str
    evidence_class: str
    fixture: bool
    stage_status: tuple[Mapping[str, Any], ...]
    missing_stages: tuple[str, ...]
    invariants: tuple[InvariantResult, ...]
    refusal_reasons: tuple[str, ...]
    physical_verified: bool
    physical_evidence_class: str | None
    authorized_control: bool
    real_intervention: bool
    controller_b_acceptance: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "trace_id": self.trace_id,
            "evidence_class": self.evidence_class,
            "fixture": self.fixture,
            "stage_status": [dict(stage) for stage in self.stage_status],
            "missing_stages": list(self.missing_stages),
            "invariants": [item.to_dict() for item in self.invariants],
            "refusal_reasons": list(self.refusal_reasons),
            "physical_verified": self.physical_verified,
            "physical_evidence_class": self.physical_evidence_class,
            "authorized_control": self.authorized_control,
            "real_intervention": self.real_intervention,
            "controller_b_acceptance": self.controller_b_acceptance,
        }


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TraceError(f"trace section {name!r} must be an object")
    return value


def _stage_status(
    trace: Mapping[str, Any],
) -> tuple[dict[str, str], tuple[str, ...]]:
    stage_status: dict[str, str] = {}
    missing: list[str] = []
    for stage in REQUIRED_STAGES:
        block = trace.get(stage)
        if isinstance(block, Mapping) and block:
            stage_status[stage] = "PRESENT"
        else:
            stage_status[stage] = "ABSENT"
            missing.append(stage)
    return stage_status, tuple(missing)


def assess_trace(trace: Mapping[str, Any]) -> TraceAssessment:
    """Assess one declared trace against the W18 invariants."""
    if not isinstance(trace, Mapping):
        raise TraceError("trace is not an object")
    if trace.get("trace_schema") != TRACE_SCHEMA:
        raise TraceError(
            f"trace schema must be {TRACE_SCHEMA!r}, got {trace.get('trace_schema')!r}"
        )
    trace_id = _text(trace.get("trace_id"))
    if not trace_id:
        raise TraceError("trace_id is missing")
    evidence_class = _text(trace.get("evidence_class"))
    if evidence_class not in {FIXTURE_EVIDENCE_CLASS, SOFTWARE_EVIDENCE_CLASS}:
        raise TraceError(
            "trace evidence class must be a declared synthetic/test class, got "
            f"{evidence_class!r}"
        )
    fixture = trace.get("fixture")
    if not isinstance(fixture, bool):
        raise TraceError("trace.fixture must be an explicit boolean")
    identity = _require_mapping(trace.get("identity"), "identity")
    run_id = _text(identity.get("run_id"))
    device_id = _text(identity.get("device_id"))
    boot_id = _text(identity.get("boot_id"))
    if not run_id or not device_id or not boot_id:
        raise TraceError("trace identity lacks run_id/device_id/boot_id")

    prediction = trace.get("prediction")
    if prediction is not None and not isinstance(prediction, Mapping):
        raise TraceError("prediction stage must be an object when present")
    warning = trace.get("warning")
    if warning is not None and not isinstance(warning, Mapping):
        raise TraceError("warning stage must be an object when present")
    policy = trace.get("policy")
    if policy is not None and not isinstance(policy, Mapping):
        raise TraceError("policy stage must be an object when present")
    command = trace.get("command")
    ack = trace.get("ack")
    applied = trace.get("applied_state")
    physical = trace.get("physical_verification")
    for name, block in (
        ("command", command),
        ("ack", ack),
        ("applied_state", applied),
        ("physical_verification", physical),
    ):
        if block is not None and not isinstance(block, Mapping):
            raise TraceError(f"{name} stage must be an object when present")
    command = command or {}
    ack = ack or {}
    applied = applied or {}
    physical = physical or {}
    prediction = prediction or {}
    warning = warning or {}
    policy = policy or {}

    stage_status, missing_stages = _stage_status(trace)
    invariants: list[InvariantResult] = []
    identity_failures: list[str] = []
    temporal_failures: list[str] = []
    authorization_failures: list[str] = []
    physical_failures: list[str] = []

    def add(
        invariant_id: str,
        requirement: str,
        passed: bool,
        observed: str,
        reason: str | None,
        ref: str,
        bucket: str,
    ) -> None:
        invariants.append(
            InvariantResult(
                invariant_id=invariant_id,
                requirement=requirement,
                status=STATUS_PASS if passed else STATUS_FAIL,
                observed=observed,
                reason_code=None if passed else reason,
                canonical_ref=ref,
            )
        )
        if not passed and reason:
            if bucket == "identity":
                identity_failures.append(reason)
            elif bucket == "temporal":
                temporal_failures.append(reason)
            elif bucket == "authorization":
                authorization_failures.append(reason)
            elif bucket == "physical":
                physical_failures.append(reason)

    # ---- TR-01/02 prediction identity --------------------------------------
    prediction_id = _text(prediction.get("prediction_id"))
    prediction_identity_ok = (
        bool(prediction)
        and bool(prediction_id)
        and _is_hex64(prediction.get("model_artifact_sha256"))
        and _is_hex64(prediction.get("feature_schema_sha256"))
        and _is_hex64(prediction.get("ordered_feature_ids_sha256"))
        and prediction.get("score_semantics") == "risk_score"
    )
    add(
        "TR-02",
        "The prediction stage must carry its own identity and risk_score semantics.",
        prediction_identity_ok,
        f"prediction_id={prediction_id or 'MISSING'}, "
        f"model={_text(prediction.get('model_artifact_sha256'))[:16] or 'MISSING'}, "
        f"schema={_text(prediction.get('feature_schema_sha256'))[:16] or 'MISSING'}",
        "PREDICTION_IDENTITY_MISSING_OR_INVALID",
        "05B §46; 02 §60.5",
        "identity",
    )

    # ---- TR-01/03/04/06 stage linkage --------------------------------------
    linkage_problems: list[str] = []
    for stage_name, block in (
        ("policy", policy),
        ("command", command),
        ("applied_state", applied),
    ):
        for key in ("run_id", "device_id", "boot_id"):
            value = block.get(key)
            if value is not None and _text(value) != _text(identity.get(key)):
                linkage_problems.append(
                    f"{stage_name} {key} does not match the trace identity"
                )
    if command:
        if not _text(command.get("command_id")):
            linkage_problems.append("command_id missing")
        if _text(command.get("prediction_id")) != prediction_id:
            linkage_problems.append("command does not reference the prediction")
        policy_decision_id = _text(policy.get("policy_decision_id"))
        if policy and _text(command.get("policy_decision_id")) != policy_decision_id:
            linkage_problems.append("command does not reference the policy decision")
    if ack and command:
        if _text(ack.get("command_id")) != _text(command.get("command_id")):
            linkage_problems.append("ACK references a different command")
        if _text(ack.get("device_id") or device_id) != device_id:
            linkage_problems.append("ACK device does not match the trace device")
        if _text(ack.get("boot_id") or boot_id) != boot_id:
            linkage_problems.append("ACK boot does not match the trace boot")
        if not isinstance(ack.get("ack_seq"), int) or isinstance(
            ack.get("ack_seq"), bool
        ):
            linkage_problems.append("ACK sequence number is missing or invalid")
    if applied and command:
        if _text(applied.get("command_id")) != _text(command.get("command_id")):
            linkage_problems.append("applied state references a different command")
    if physical and command:
        if _text(physical.get("command_id")) != _text(command.get("command_id")):
            linkage_problems.append("physical verification references a different command")
    add(
        "TR-01",
        "Run/device/boot lineage and command/prediction/policy/ACK identities must agree.",
        not linkage_problems,
        "; ".join(linkage_problems) or "all present stages agree",
        "CROSS_STAGE_IDENTITY_MISMATCH",
        "02 §4.2; 05B §46",
        "identity",
    )

    physical_identity: list[str] = []
    for key in ("run_id", "device_id", "boot_id"):
        value = physical.get(key)
        if value is not None and _text(value) != _text(identity.get(key)):
            physical_identity.append(f"physical {key} does not match the trace")
    add(
        "TR-08",
        "Physical evidence may not be attributed across runs, devices or boots.",
        not physical_identity,
        "; ".join(physical_identity) or "physical attribution matches the trace identity",
        "PHYSICAL_ATTRIBUTION_ACROSS_RUNS",
        "01 §1.7; 05B §46",
        "identity",
    )

    terminal_problems: list[str] = []
    command_status = _text(command.get("status"))
    ack_status = _text(ack.get("ack_status"))
    if command_status in TERMINAL_COMMAND_SUCCESS and ack_status in ACK_REJECTED_STATUSES:
        terminal_problems.append("command success contradicts ACK rejection")
    if command_status in TERMINAL_COMMAND_FAILURE and ack_status in ACK_ACCEPTED_STATUSES:
        terminal_problems.append("command failure contradicts ACK acceptance")
    if ack_status in ACK_REJECTED_STATUSES and applied.get("applied_cooling") not in (
        None,
        False,
    ):
        terminal_problems.append("rejected ACK contradicts an applied cooling state")
    if physical.get("observed") is False and physical.get("claimed_verified") is True:
        terminal_problems.append("physical response claims verified while observed=false")
    add(
        "TR-07",
        "Terminal command/ACK/applied/physical states must not contradict each other.",
        not terminal_problems,
        "; ".join(terminal_problems) or "terminal states are consistent",
        "TERMINAL_STATUS_CONTRADICTION",
        "02 §1.6; 01 §1.4",
        "identity",
    )

    # ---- TR-05 chronology ---------------------------------------------------
    chronology_problems: list[str] = []
    anchor_event = prediction.get("prediction_anchor_event_s")
    receipt = prediction.get("prediction_receipt_s")
    warning_time = warning.get("aware_event_s")
    policy_time = policy.get("decision_event_s")
    command_time = command.get("issued_event_s")
    ack_time = ack.get("acknowledged_event_s")
    applied_time = applied.get("reported_event_s")
    electrical = physical.get("electrical_response")
    thermal = physical.get("thermal_response")
    electrical_time = (
        electrical.get("observation_event_s")
        if isinstance(electrical, Mapping)
        else None
    )
    thermal_time = (
        thermal.get("observation_event_s")
        if isinstance(thermal, Mapping)
        else None
    )
    ordered_times = [
        (STAGE_PREDICTION, receipt if _is_finite_number(receipt) else anchor_event),
        (STAGE_WARNING, warning_time),
        (STAGE_POLICY, policy_time),
        (STAGE_COMMAND, command_time),
        (STAGE_ACK, ack_time),
        (STAGE_APPLIED, applied_time),
        ("electrical_response", electrical_time),
        ("thermal_response", thermal_time),
    ]
    chain: list[tuple[str, float]] = []
    for stage, value in ordered_times:
        if stage == STAGE_PREDICTION and not prediction:
            continue
        if stage == STAGE_WARNING and not warning:
            continue
        if stage == STAGE_POLICY and not policy:
            continue
        if stage == STAGE_COMMAND and not command:
            continue
        if stage == STAGE_ACK and not ack:
            continue
        if stage == STAGE_APPLIED and not applied:
            continue
        if stage in ("electrical_response", "thermal_response") and not physical:
            continue
        if _is_finite_number(value):
            chain.append((stage, float(value)))
    for previous, current in zip(chain, chain[1:]):
        if current[1] < previous[1]:
            chronology_problems.append(
                f"{current[0]} precedes {previous[0]}"
            )
    for stage, value in (
        (STAGE_PREDICTION, anchor_event),
        (STAGE_WARNING, warning_time),
        (STAGE_POLICY, policy_time),
        (STAGE_COMMAND, command_time),
        (STAGE_ACK, ack_time),
    ):
        block = trace.get(stage)
        if not isinstance(block, Mapping) or not block:
            continue
        if not _is_finite_number(value):
            chronology_problems.append(f"{stage} event time missing")
        if stage == STAGE_PREDICTION and not _is_finite_number(receipt):
            chronology_problems.append("prediction receipt time invalid")
    add(
        "TR-05",
        "Prediction, warning, policy, command, ACK, electrical and thermal times must follow causal order.",
        not chronology_problems,
        "; ".join(chronology_problems) or "chronology is coherent",
        "CAUSAL_ORDER_VIOLATION",
        "02 §5; 01 §1.5-1.6",
        "temporal",
    )

    # ---- TR-11 authorization ------------------------------------------------
    policy_status = _text(policy.get("decision_status"))
    authorization_problems: list[str] = []
    authorized_control = False
    if policy and policy_status not in POLICY_STATUSES:
        authorization_problems.append(
            f"unknown policy decision status {policy_status or 'MISSING'}"
        )
    if policy_status == POLICY_AUTHORIZED:
        authorization = policy.get("authorization")
        if not isinstance(authorization, Mapping):
            authorization_problems.append("authorized decision lacks authorization evidence")
        else:
            if not _text(authorization.get("authority_id")):
                authorization_problems.append("authorization authority is missing")
            if not _is_hex64(authorization.get("evidence_sha256")):
                authorization_problems.append("authorization evidence hash is missing")
            if not _is_finite_number(authorization.get("authorized_event_s")):
                authorization_problems.append("authorization event time is missing")
        if not authorization_problems:
            authorized_control = True
    if command:
        if command.get("dispatchable") is True:
            authorization_problems.append("command declares dispatchable=true")
        if _text(command.get("transport")) not in (
            "NONE_TEST_FIXTURE",
            "NONE",
            "",
        ):
            authorization_problems.append("command declares a transport path")
        if policy_status == POLICY_NOT_EVALUATED:
            authorization_problems.append(
                "command stage exists but policy was never evaluated"
            )
        if policy_status == POLICY_HYPOTHETICAL:
            if command.get("hypothetical_test_record") is not True:
                authorization_problems.append(
                    "command is not marked as a hypothetical test record"
                )
            if not _text(command.get("destination", "")).startswith("TEST_ONLY"):
                authorization_problems.append(
                    "hypothetical command has a non-test destination"
                )
    if policy_status == POLICY_NOT_EVALUATED and (
        ack or applied or physical
    ):
        authorization_problems.append(
            "downstream stages exist without any policy evaluation"
        )
    if command and not policy:
        authorization_problems.append("command exists without a policy decision")
    if not command and (ack or applied or physical):
        authorization_problems.append(
            "downstream stage exists without a command"
        )
    add(
        "TR-11",
        "A command-bearing trace must carry an explicit authorized decision; hypothetical records stay non-dispatchable.",
        not authorization_problems,
        "; ".join(authorization_problems) or f"policy status {policy_status or 'ABSENT'}",
        "COMMAND_WITHOUT_AUTHORIZATION_EVIDENCE",
        "02 §1.6; 05B §46; 04 §33",
        "authorization",
    )

    # ---- TR-06/09 physical verification ------------------------------------
    physical_failures_local: list[str] = []
    physical_verified = False
    physical_evidence_class: str | None = None
    if physical:
        physical_evidence_class = _text(physical.get("evidence_class")) or None
        if fixture:
            if physical_evidence_class != PHYSICAL_FIXTURE_EVIDENCE_CLASS:
                physical_failures_local.append(
                    "fixture physical evidence class is not the declared test class"
                )
        elif physical_evidence_class not in PHYSICAL_EVIDENCE_CLASSES:
            physical_failures_local.append(
                f"physical evidence class {physical_evidence_class!r} is not qualified"
            )
        for name, block in (
            ("electrical_response", electrical),
            ("thermal_response", thermal),
        ):
            if not isinstance(block, Mapping):
                physical_failures_local.append(f"{name} missing")
                continue
            if block.get("observed") is not True:
                physical_failures_local.append(f"{name} not observed")
            if not _is_finite_number(block.get("observation_event_s")):
                physical_failures_local.append(f"{name} observation time missing")
            if _text(block.get("quality")) not in TRUSTED_QUALITY:
                physical_failures_local.append(f"{name} quality provenance not trusted")
            if not _text(block.get("calibration_id")):
                physical_failures_local.append(f"{name} calibration identity missing")
            child_class = _text(block.get("evidence_class"))
            if fixture:
                if child_class not in {
                    FIXTURE_EVIDENCE_CLASS,
                    PHYSICAL_FIXTURE_EVIDENCE_CLASS,
                }:
                    physical_failures_local.append(
                        f"{name} evidence class contradicts the fixture"
                    )
            elif child_class not in PHYSICAL_EVIDENCE_CLASSES:
                physical_failures_local.append(
                    f"{name} evidence class is not measured physical evidence"
                )
        if physical.get("independent_of_ack") is not True:
            physical_failures_local.append("physical evidence is not independent of the ACK")
        if not fixture and not physical_failures_local:
            physical_verified = True
        add(
            "TR-06",
            "Physical verification requires qualified electrical and thermal evidence with provenance.",
            not physical_failures_local,
            "; ".join(physical_failures_local)
            or (
                "qualified physical evidence present"
                if physical_verified
                else "structurally complete synthetic fixture evidence"
            ),
            "PHYSICAL_EVIDENCE_INCOMPLETE",
            "01 §1.5-1.7; 03 §1.3",
            "physical",
        )
    else:
        downstream_present = bool(command or ack or applied)
        claimed_success = trace.get("claimed_physical_success") is True
        shortcut_problem = None
        if claimed_success:
            shortcut_problem = (
                "trace claims physical success without an independent physical stage"
            )
        elif downstream_present:
            shortcut_problem = (
                "applied state / ACK present without independent physical verification"
            )
        add(
            "TR-09",
            "An ACK or applied-state report is never physical verification.",
            shortcut_problem is None,
            shortcut_problem or "no ACK-to-physical-success shortcut",
            "ACK_IS_NOT_PHYSICAL_EVIDENCE",
            "01 §1.4; 02 §1.6; 05B §46",
            "physical",
        )

    # ---- TR-10 missing-stage explicitness ----------------------------------
    add(
        "TR-10",
        "Every absent stage must be reported explicitly, never silently treated as PASS.",
        True,
        "missing stages: " + (", ".join(missing_stages) if missing_stages else "none"),
        None,
        "05B §46",
        "identity",
    )
    synthetic_mislabeled = (
        not fixture
        and physical_evidence_class
        in {PHYSICAL_FIXTURE_EVIDENCE_CLASS, FIXTURE_EVIDENCE_CLASS}
    )
    fixture_claim_violation = fixture and (
        evidence_class != FIXTURE_EVIDENCE_CLASS
        or trace.get("claimed_physical_success") is True
    )
    add(
        "TR-12",
        "A fixture must be explicitly labeled TEST_ONLY and must not claim a real intervention.",
        not synthetic_mislabeled and not fixture_claim_violation,
        f"fixture={fixture}, evidence_class={evidence_class}, "
        f"physical_evidence_class={physical_evidence_class}, "
        f"claimed_physical_success={trace.get('claimed_physical_success')}",
        (
            "SYNTHETIC_FIXTURE_MISLABELED_AS_REAL"
            if synthetic_mislabeled
            else "FIXTURE_LABEL_OR_CLAIM_INVALID"
        ),
        "05B §46 fixture hygiene",
        "identity",
    )

    refusal_reasons = tuple(
        dict.fromkeys(
            identity_failures
            + temporal_failures
            + authorization_failures
            + physical_failures
        )
    )
    if identity_failures:
        outcome = TRACE_INCONSISTENT_IDENTITY
    elif temporal_failures:
        outcome = TRACE_TEMPORAL_CONTRADICTION
    elif authorization_failures:
        outcome = TRACE_NOT_AUTHORIZED
    elif physical_failures:
        outcome = TRACE_PHYSICAL_UNVERIFIED
    elif missing_stages:
        outcome = TRACE_PARTIAL_MISSING_EVIDENCE
    elif fixture:
        outcome = TRACE_COMPLETE_SOFTWARE_FIXTURE
    else:
        outcome = TRACE_COMPLETE_PENDING_HUMAN_ACCEPTANCE
    return TraceAssessment(
        outcome=outcome,
        trace_id=trace_id,
        evidence_class=evidence_class,
        fixture=fixture,
        stage_status=tuple(
            {"stage": stage, "status": status}
            for stage, status in stage_status.items()
        ),
        missing_stages=missing_stages,
        invariants=tuple(invariants),
        refusal_reasons=refusal_reasons,
        physical_verified=physical_verified,
        physical_evidence_class=physical_evidence_class,
        authorized_control=authorized_control,
        real_intervention=False,
    )


def build_test_only_fixture(
    *,
    model_artifact_sha256: str,
    feature_schema_sha256: str,
    ordered_feature_ids_sha256: str,
) -> dict[str, Any]:
    """A small synthetic trace used only to exercise parsing and invariants."""
    feature_vector_sha256 = hashlib.sha256(
        b"w18-test-only-feature-vector-v1"
    ).hexdigest()
    return {
        "trace_schema": TRACE_SCHEMA,
        "trace_id": "trace-w18-test-only-0001",
        "evidence_class": FIXTURE_EVIDENCE_CLASS,
        "fixture": True,
        "claimed_physical_success": False,
        "identity": {
            "run_id": "run-w18-test-0001",
            "device_id": "device-w18-test",
            "boot_id": "boot-w18-test-1",
        },
        "prediction": {
            "prediction_id": "pred-w18-test-0001",
            "prediction_anchor_event_s": 100.0,
            "prediction_receipt_s": 100.25,
            "risk_score": 0.82,
            "score_semantics": "risk_score",
            "model_artifact_sha256": model_artifact_sha256,
            "feature_schema_sha256": feature_schema_sha256,
            "ordered_feature_ids_sha256": ordered_feature_ids_sha256,
            "feature_vector_sha256": feature_vector_sha256,
            "input_quality": "TRUSTED_TEST_FIXTURE",
            "input_telemetry_ids": ["tel-w18-test-1", "tel-w18-test-2"],
            "evidence_class": SOFTWARE_EVIDENCE_CLASS,
        },
        "warning": {
            "warning_rule_id": "w18-test-only-warning-rule",
            "warning_status": "TRIGGERED_SYNTHETIC_ILLUSTRATIVE",
            "threshold": 0.5,
            "threshold_status": "ILLUSTRATIVE_NOT_FROZEN",
            "persistence": "NOT_FROZEN",
            "persistence_status": "NOT_FROZEN",
            "policy_version": "coldguard-w18-test-only-policy-v1",
            "aware_event_s": 100.5,
        },
        "policy": {
            "policy_decision_id": "policy-w18-test-0001",
            "policy_version": "coldguard-w18-test-only-policy-v1",
            "run_id": "run-w18-test-0001",
            "device_id": "device-w18-test",
            "boot_id": "boot-w18-test-1",
            "decision_status": POLICY_HYPOTHETICAL,
            "reason_code": "TEST_ONLY_HYPOTHETICAL_PREDICTIVE_POLICY",
            "safety_gate": "TEST_ONLY_NOT_AUTHORIZED",
            "decision_event_s": 100.75,
            "authorization": None,
            "dispatchable": False,
        },
        "command": {
            "command_id": "cmd-w18-test-0001",
            "run_id": "run-w18-test-0001",
            "device_id": "device-w18-test",
            "prediction_id": "pred-w18-test-0001",
            "policy_decision_id": "policy-w18-test-0001",
            "action": "COOLING_ON",
            "duty": 0.5,
            "status": "HYPOTHETICAL_TEST_RECORD",
            "destination": "TEST_ONLY_NO_DESTINATION",
            "transport": "NONE_TEST_FIXTURE",
            "hypothetical_test_record": True,
            "dispatchable": False,
            "issued_event_s": 101.0,
        },
        "ack": {
            "command_id": "cmd-w18-test-0001",
            "ack_status": "ACCEPTED_TEST_FIXTURE",
            "acknowledged_event_s": 101.5,
            "device_id": "device-w18-test",
            "boot_id": "boot-w18-test-1",
            "ack_seq": 41,
            "evidence_class": FIXTURE_EVIDENCE_CLASS,
        },
        "applied_state": {
            "command_id": "cmd-w18-test-0001",
            "applied_cooling": True,
            "applied_duty": 0.5,
            "reported_event_s": 101.75,
            "independent_evidence": False,
            "source": "TEST_FIXTURE_DEVICE_REPORT",
        },
        "physical_verification": {
            "command_id": "cmd-w18-test-0001",
            "run_id": "run-w18-test-0001",
            "device_id": "device-w18-test",
            "boot_id": "boot-w18-test-1",
            "independent_of_ack": True,
            "evidence_class": PHYSICAL_FIXTURE_EVIDENCE_CLASS,
            "electrical_response": {
                "observed": True,
                "power_w": 41.2,
                "observation_event_s": 102.0,
                "quality": "TRUSTED_TEST_FIXTURE",
                "calibration_id": "TEST_CAL_001",
                "evidence_class": FIXTURE_EVIDENCE_CLASS,
            },
            "thermal_response": {
                "observed": True,
                "delta_c": -0.4,
                "observation_event_s": 160.0,
                "quality": "TRUSTED_TEST_FIXTURE",
                "calibration_id": "TEST_CAL_001",
                "evidence_class": FIXTURE_EVIDENCE_CLASS,
            },
        },
    }


@dataclass(frozen=True)
class W17ReplaySummary:
    trace_schema: str
    record_count: int
    trace_sha256: str
    trace_sha256_valid: bool
    model_artifact_sha256: str
    freshness_verdict_counts: Mapping[str, int]
    warning_status_counts: Mapping[str, int]
    policy_status_counts: Mapping[str, int]
    policy_violation_count: int
    stage_status: Mapping[str, str]
    missing_stages: tuple[str, ...]
    outcome: str
    physical_chain_status: str
    physical_control_capability: bool
    evidence_class: str
    records_copied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_schema": self.trace_schema,
            "record_count": self.record_count,
            "trace_sha256": self.trace_sha256,
            "trace_sha256_valid": self.trace_sha256_valid,
            "model_artifact_sha256": self.model_artifact_sha256,
            "freshness_verdict_counts": dict(self.freshness_verdict_counts),
            "warning_status_counts": dict(self.warning_status_counts),
            "policy_status_counts": dict(self.policy_status_counts),
            "policy_violation_count": self.policy_violation_count,
            "stage_status": dict(self.stage_status),
            "missing_stages": list(self.missing_stages),
            "outcome": self.outcome,
            "physical_chain_status": self.physical_chain_status,
            "physical_control_capability": self.physical_control_capability,
            "evidence_class": self.evidence_class,
            "records_copied": self.records_copied,
        }


def summarize_w17_replay_trace(payload: Mapping[str, Any]) -> W17ReplaySummary:
    """Assess the W17 replay trace without copying its 783 detailed records."""
    if not isinstance(payload, Mapping):
        raise TraceError("W17 trace payload is not an object")
    if payload.get("trace_schema") != W17_TRACE_SCHEMA:
        raise TraceError("not a W17 shadow trace payload")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise TraceError("W17 trace has no records")
    if payload.get("record_count") != len(records):
        raise TraceError("W17 trace record_count does not match the records array")
    body = {
        "header": payload.get("header"),
        "record_count": payload.get("record_count"),
        "records": records,
        "trace_schema": payload.get("trace_schema"),
    }
    computed_sha = _canonical_sha256(body)
    if computed_sha != payload.get("trace_sha256"):
        raise TraceError("W17 trace internal hash does not bind its content")
    header = _require_mapping(payload.get("header"), "header")
    model = _require_mapping(header.get("model"), "header.model")
    freshness_counts: dict[str, int] = {}
    warning_counts: dict[str, int] = {}
    policy_counts: dict[str, int] = {}
    policy_violations = 0
    for record in records:
        if not isinstance(record, Mapping):
            raise TraceError("W17 trace contains a non-object record")
        freshness = _require_mapping(record.get("freshness"), "record.freshness")
        verdict = _text(freshness.get("verdict"))
        freshness_counts[verdict] = freshness_counts.get(verdict, 0) + 1
        warning = record.get("hypothetical_warning")
        warning_status = (
            _text(warning.get("status")) if isinstance(warning, Mapping) else "MISSING"
        )
        warning_counts[warning_status] = warning_counts.get(warning_status, 0) + 1
        policy = record.get("hypothetical_policy")
        if not isinstance(policy, Mapping):
            policy_violations += 1
            policy_status = "MISSING"
        else:
            policy_status = _text(policy.get("status"))
            if policy.get("dispatchable") is not False:
                policy_violations += 1
        policy_counts[policy_status] = policy_counts.get(policy_status, 0) + 1
    physical_capability = header.get("physical_control_capability")
    if physical_capability is not False:
        raise TraceError("W17 trace declares physical control capability")
    stage_status = {
        STAGE_PREDICTION: "PRESENT",
        STAGE_WARNING: "PRESENT_SYNTHETIC_ILLUSTRATIVE",
        STAGE_POLICY: "HYPOTHETICAL_ONLY_NOT_EVALUATED",
        STAGE_COMMAND: "ABSENT",
        STAGE_ACK: "ABSENT",
        STAGE_APPLIED: "ABSENT",
        STAGE_PHYSICAL: "ABSENT",
    }
    missing_stages = (
        STAGE_COMMAND,
        STAGE_ACK,
        STAGE_APPLIED,
        STAGE_PHYSICAL,
    )
    return W17ReplaySummary(
        trace_schema=W17_TRACE_SCHEMA,
        record_count=len(records),
        trace_sha256=str(payload.get("trace_sha256")),
        trace_sha256_valid=True,
        model_artifact_sha256=_text(model.get("model_artifact_sha256")),
        freshness_verdict_counts=dict(sorted(freshness_counts.items())),
        warning_status_counts=dict(sorted(warning_counts.items())),
        policy_status_counts=dict(sorted(policy_counts.items())),
        policy_violation_count=policy_violations,
        stage_status=stage_status,
        missing_stages=missing_stages,
        outcome=TRACE_PARTIAL_MISSING_EVIDENCE,
        physical_chain_status=(
            "PHYSICAL_CHAIN_UNAVAILABLE_NO_AUTHORIZED_POLICY_COMMAND_STAGE"
        ),
        physical_control_capability=False,
        evidence_class=SOFTWARE_EVIDENCE_CLASS,
    )
