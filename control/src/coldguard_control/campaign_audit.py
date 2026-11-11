"""Pure campaign audit module for Member D (W20).

Implements Doc 05D section 52 (Week 20, final paired A/B campaign wave 2)
as a pure decision layer:

- D-W20-02: every valid Controller B run is audited for prediction presence,
  policy decision trace, command, ACK and physical verification; every valid
  Controller A run is audited for a correct reactive trigger.
- D-W20-03: the campaign anomaly report lists rejected commands,
  verification failures, SAFE_LOCAL events and control anomalies.
- D-W20-04: G5 control readiness is computed only when the final campaign has
  at least one valid A run and one valid B run, every valid run passes the
  audit, and each controller used exactly one frozen policy version
  (D-W20-01: no policy drift, no change "for better results").

Audit semantics:
- Only records marked ``valid`` are audited (invalid runs are excluded and
  listed; they never silently drop out of the policy-freeze check below).
- A valid run passes when it has no audit findings. For B runs that means the
  five evidence fields are present; for A runs that means the reactive
  trigger was correct. A valid run also fails on verification failure or a
  control anomaly. Rejected commands and SAFE_LOCAL events are listed in the
  anomaly report but do not by themselves fail a run: both are expected
  campaign outcomes, not evidence defects.
- The single-frozen-policy-version check applies to every record of the
  campaign (valid or not): any run under a different policy version is drift.

Authority rules (consistent with W19 ``campaign_integrity``):
- Pure decision layer: no transport, database, GPIO, web or clock imports.
- Makes no physical or transport claims; outputs are evidence listings only.
- Never edits, mutates or silently corrects input evidence (Doc 03 / 05D).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .campaign_integrity import ControllerVariant


class AuditAnomalyCategory(str, Enum):
    """Campaign anomaly categories listed by D-W20-03."""

    REJECTED_COMMAND = "REJECTED_COMMAND"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    SAFE_LOCAL_EVENT = "SAFE_LOCAL_EVENT"
    CONTROL_ANOMALY = "CONTROL_ANOMALY"


@dataclass(frozen=True, slots=True)
class AnomalyEntry:
    """One listed anomaly; immutable and evidence-preserving."""

    category: AuditAnomalyCategory
    run_id: str
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, AuditAnomalyCategory):
            raise TypeError(
                "category must be an AuditAnomalyCategory, "
                f"got {type(self.category).__name__}"
            )
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("detail must be a non-empty string")


@dataclass(frozen=True, slots=True)
class CampaignAuditRecord:
    """Evidence for one campaign run, as audited by D-W20-02/D-W20-03.

    The five ``*_present`` fields are audited only for valid Controller B
    runs; ``reactive_trigger_correct`` only for valid Controller A runs.
    The anomaly fields (``rejected_command_reasons``, ``verification_failed``,
    ``safe_local_event_count``, ``control_anomaly``) are reported for every
    record in the campaign.
    """

    run_id: str
    controller: ControllerVariant
    policy_version: str
    valid: bool
    prediction_present: bool
    policy_trace_present: bool
    command_present: bool
    ack_present: bool
    physical_verification_present: bool
    reactive_trigger_correct: bool
    rejected_command_reasons: tuple[str, ...]
    verification_failed: bool
    safe_local_event_count: int
    control_anomaly: bool

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.controller, ControllerVariant):
            raise TypeError(
                "controller must be a ControllerVariant, "
                f"got {type(self.controller).__name__}"
            )
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be a non-empty string")
        if not isinstance(self.valid, bool):
            raise TypeError(f"valid must be a strict boolean, got {type(self.valid).__name__}")

        for name in (
            "prediction_present",
            "policy_trace_present",
            "command_present",
            "ack_present",
            "physical_verification_present",
            "reactive_trigger_correct",
            "verification_failed",
            "control_anomaly",
        ):
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise TypeError(
                    f"{name} must be a strict boolean, got {type(value).__name__}"
                )

        if not isinstance(self.rejected_command_reasons, tuple):
            raise TypeError(
                "rejected_command_reasons must be a tuple of strings, "
                f"got {type(self.rejected_command_reasons).__name__}"
            )
        for reason in self.rejected_command_reasons:
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(
                    "rejected_command_reasons entries must be non-empty strings"
                )

        if (
            isinstance(self.safe_local_event_count, bool)
            or not isinstance(self.safe_local_event_count, int)
            or self.safe_local_event_count < 0
        ):
            raise ValueError("safe_local_event_count must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class CampaignAuditDecision:
    """Result of the pure W20 campaign audit."""

    audited_run_ids: tuple[str, ...]
    excluded_invalid_run_ids: tuple[str, ...]
    audit_findings: tuple[str, ...]
    anomalies: tuple[AnomalyEntry, ...]
    a_policy_versions: tuple[str, ...]
    b_policy_versions: tuple[str, ...]
    g5_ready: bool
    g5_blockers: tuple[str, ...]
    silently_corrected: bool = False


def audit_campaign(records: Sequence[CampaignAuditRecord]) -> CampaignAuditDecision:
    """Audit a final A/B campaign and compute G5 control readiness.

    Pure function: never edits input evidence, never emits a physical or
    transport claim. G5 readiness is granted only when the campaign has at
    least one valid A run and one valid B run, every valid run passes the
    audit, and each controller used exactly one frozen policy version.
    """
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise TypeError(
            f"records must be a Sequence of CampaignAuditRecord, got {type(records).__name__}"
        )
    records_list: list[CampaignAuditRecord] = list(records)
    if not records_list:
        raise ValueError("records must be non-empty; an empty campaign is not auditable")

    seen_run_ids: set[str] = set()
    for record in records_list:
        if not isinstance(record, CampaignAuditRecord):
            raise TypeError(
                f"each record must be a CampaignAuditRecord, got {type(record).__name__}"
            )
        if record.run_id in seen_run_ids:
            raise ValueError(f"duplicate run_id: {record.run_id}")
        seen_run_ids.add(record.run_id)

    valid_runs = [r for r in records_list if r.valid]
    audit_findings: list[str] = []

    # D-W20-02: audit every valid Controller B run.
    for record in valid_runs:
        if record.controller is ControllerVariant.B:
            if not record.prediction_present:
                audit_findings.append(f"{record.run_id}:MISSING_PREDICTION")
            if not record.policy_trace_present:
                audit_findings.append(f"{record.run_id}:MISSING_POLICY_TRACE")
            if not record.command_present:
                audit_findings.append(f"{record.run_id}:MISSING_COMMAND")
            if not record.ack_present:
                audit_findings.append(f"{record.run_id}:MISSING_ACK")
            if not record.physical_verification_present:
                audit_findings.append(f"{record.run_id}:MISSING_PHYSICAL_VERIFICATION")

    # D-W20-02: audit every valid Controller A run.
    for record in valid_runs:
        if record.controller is ControllerVariant.A and not record.reactive_trigger_correct:
            audit_findings.append(f"{record.run_id}:INCORRECT_REACTIVE_TRIGGER")

    # A valid run with a verification failure or control anomaly does not pass.
    for record in valid_runs:
        if record.verification_failed:
            audit_findings.append(f"{record.run_id}:VERIFICATION_FAILED")
        if record.control_anomaly:
            audit_findings.append(f"{record.run_id}:CONTROL_ANOMALY")

    # D-W20-03: campaign anomaly report (all records, evidence untouched).
    anomalies: list[AnomalyEntry] = []
    for record in records_list:
        for reason in record.rejected_command_reasons:
            anomalies.append(
                AnomalyEntry(AuditAnomalyCategory.REJECTED_COMMAND, record.run_id, reason)
            )
        if record.verification_failed:
            anomalies.append(
                AnomalyEntry(
                    AuditAnomalyCategory.VERIFICATION_FAILURE, record.run_id, "VERIFICATION_FAILED"
                )
            )
        if record.safe_local_event_count > 0:
            anomalies.append(
                AnomalyEntry(
                    AuditAnomalyCategory.SAFE_LOCAL_EVENT,
                    record.run_id,
                    f"SAFE_LOCAL_EVENTS={record.safe_local_event_count}",
                )
            )
        if record.control_anomaly:
            anomalies.append(
                AnomalyEntry(AuditAnomalyCategory.CONTROL_ANOMALY, record.run_id, "CONTROL_ANOMALY")
            )

    # D-W20-01: frozen policy check across every campaign record (valid or not).
    a_policy_versions = tuple(
        sorted({r.policy_version for r in records_list if r.controller is ControllerVariant.A})
    )
    b_policy_versions = tuple(
        sorted({r.policy_version for r in records_list if r.controller is ControllerVariant.B})
    )

    # D-W20-04: G5 control readiness.
    g5_blockers: list[str] = []
    if not any(r.controller is ControllerVariant.A and r.valid for r in records_list):
        g5_blockers.append("NO_VALID_CONTROLLER_A_RUN")
    if not any(r.controller is ControllerVariant.B and r.valid for r in records_list):
        g5_blockers.append("NO_VALID_CONTROLLER_B_RUN")
    if audit_findings:
        g5_blockers.append(f"NOT_ALL_VALID_RUNS_PASS: {len(audit_findings)} finding(s)")
    if len(a_policy_versions) > 1:
        g5_blockers.append(
            f"MULTIPLE_CONTROLLER_A_POLICY_VERSIONS: {', '.join(a_policy_versions)}"
        )
    if len(b_policy_versions) > 1:
        g5_blockers.append(
            f"MULTIPLE_CONTROLLER_B_POLICY_VERSIONS: {', '.join(b_policy_versions)}"
        )

    return CampaignAuditDecision(
        audited_run_ids=tuple(r.run_id for r in valid_runs),
        excluded_invalid_run_ids=tuple(r.run_id for r in records_list if not r.valid),
        audit_findings=tuple(audit_findings),
        anomalies=tuple(anomalies),
        a_policy_versions=a_policy_versions,
        b_policy_versions=b_policy_versions,
        g5_ready=not g5_blockers,
        g5_blockers=tuple(g5_blockers),
        silently_corrected=False,
    )
