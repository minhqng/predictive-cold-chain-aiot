"""Pure campaign-integrity module for Member D (W19).

Enforces controller identity locks, policy/config locks, and action/failure
behavior; detects adaptive tuning, duplicate logical commands, nonsensical
verification states, and control anomalies; flags runs without silently
correcting data; and preserves pair_id/policy evidence for Member B's pair
ledger.

Authority rules:
- Controller variant is strictly ControllerVariant.A or ControllerVariant.B.
- Pure decision layer: no imports of transport, database, GPIO, web or clock modules.
- No physical actuation commands are ever emitted.
- Never alters, mutates, or silently corrects input evidence (Doc 03 / Doc 05D W19).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping


class ControllerVariant(str, Enum):
    """Normative controller variant locked during A/B campaign."""

    A = "A"
    B = "B"
    CONTROLLER_A = "A"
    CONTROLLER_B = "B"


class CampaignAssessmentStatus(str, Enum):
    """Campaign run assessment status under Doc 03 / Doc 05D rules."""

    ACCEPTED = "ACCEPTED"
    FLAGGED = "FLAGGED"


def _validate_sha256(name: str, value: object) -> str:
    """Validate that value is a strict 64-character hex SHA-256 string."""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, got {type(value).__name__}")
    val = value.strip().lower()
    if len(val) != 64 or not all(c in "0123456789abcdef" for c in val):
        raise ValueError(
            f"{name} must be a valid 64-character hex SHA-256 string, got {value!r}"
        )
    return val


def compute_config_sha256(config_payload: Mapping[str, Any] | str | bytes) -> str:
    """Compute a deterministic lowercase 64-hex SHA-256 digest of config payload."""
    if isinstance(config_payload, bytes):
        raw_bytes = config_payload
    elif isinstance(config_payload, str):
        raw_bytes = config_payload.encode("utf-8")
    elif isinstance(config_payload, Mapping):
        raw_bytes = json.dumps(
            config_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    else:
        raise TypeError(
            f"config_payload must be Mapping, str, or bytes, got {type(config_payload).__name__}"
        )
    return hashlib.sha256(raw_bytes).hexdigest()


@dataclass(frozen=True, slots=True)
class FrozenControllerIdentity:
    """Exact frozen controller identity, policy version, and behavior locks."""

    controller: ControllerVariant
    policy_version: str
    config_sha256: str
    action_profile: str
    failure_policy: str

    def __post_init__(self) -> None:
        if not isinstance(self.controller, ControllerVariant):
            raise TypeError(
                f"controller must be a ControllerVariant, got {type(self.controller).__name__}"
            )
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be a non-empty string")
        object.__setattr__(
            self, "config_sha256", _validate_sha256("config_sha256", self.config_sha256)
        )
        if not isinstance(self.action_profile, str) or not self.action_profile.strip():
            raise ValueError("action_profile must be a non-empty string")
        if not isinstance(self.failure_policy, str) or not self.failure_policy.strip():
            raise ValueError("failure_policy must be a non-empty string")


@dataclass(frozen=True, slots=True)
class RunEvidence:
    """Audit evidence collected from a single campaign run."""

    run_id: str
    pair_id: str | None
    controller: ControllerVariant
    policy_version: str
    config_sha256: str
    action_profile: str
    failure_policy: str
    tuning_changed: bool
    duplicate_logical_command: bool
    verification_sensible: bool
    control_anomaly: bool

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if self.pair_id is not None:
            if not isinstance(self.pair_id, str) or not self.pair_id.strip():
                raise ValueError("pair_id must be a non-empty string or None")
        if not isinstance(self.controller, ControllerVariant):
            raise TypeError(
                f"controller must be a ControllerVariant, got {type(self.controller).__name__}"
            )
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be a non-empty string")
        object.__setattr__(
            self, "config_sha256", _validate_sha256("config_sha256", self.config_sha256)
        )
        if not isinstance(self.action_profile, str) or not self.action_profile.strip():
            raise ValueError("action_profile must be a non-empty string")
        if not isinstance(self.failure_policy, str) or not self.failure_policy.strip():
            raise ValueError("failure_policy must be a non-empty string")

        boolean_fields = (
            "tuning_changed",
            "duplicate_logical_command",
            "verification_sensible",
            "control_anomaly",
        )
        for name in boolean_fields:
            val = getattr(self, name)
            if not isinstance(val, bool):
                raise TypeError(
                    f"{name} must be a strict boolean, got {type(val).__name__}"
                )


@dataclass(frozen=True, slots=True)
class PairLedgerRecord:
    """Immutable per-run record preserving pair_id/policy evidence for B's pair ledger."""

    pair_id: str | None
    run_id: str
    controller: ControllerVariant
    policy_version: str
    config_sha256: str
    action_profile: str
    failure_policy: str
    assessment_status: CampaignAssessmentStatus
    flagged_reasons: tuple[str, ...]
    silently_corrected: bool = False


@dataclass(frozen=True, slots=True)
class CampaignAssessmentDecision:
    """Result of pure campaign run assessment."""

    status: CampaignAssessmentStatus
    reasons: tuple[str, ...]
    ledger_record: PairLedgerRecord
    physical_command_emitted: bool = False
    silently_corrected: bool = False


@dataclass(frozen=True, slots=True)
class PairedCampaignRecord:
    """Immutable paired record supporting Member B's A/B pair ledger."""

    pair_id: str
    run_a: PairLedgerRecord
    run_b: PairLedgerRecord
    pair_status: CampaignAssessmentStatus
    pair_reasons: tuple[str, ...]
    silently_corrected: bool = False


@dataclass(frozen=True, slots=True)
class PairedCampaignDecision:
    """Result of pure paired campaign assessment."""

    pair_status: CampaignAssessmentStatus
    pair_reasons: tuple[str, ...]
    record: PairedCampaignRecord
    physical_command_emitted: bool = False
    silently_corrected: bool = False


def assess_campaign_run(
    evidence: RunEvidence,
    frozen_identity: FrozenControllerIdentity,
) -> CampaignAssessmentDecision:
    """Assess a campaign run against frozen identity and integrity rules.

    Pure function: checks controller identity, policy version, config digest,
    action profile, failure response, adaptive tuning, duplicate logical commands,
    verification state plausibility, and control anomalies.
    Never alters or silently corrects input evidence.
    """
    if not isinstance(evidence, RunEvidence):
        raise TypeError(
            f"evidence must be RunEvidence, got {type(evidence).__name__}"
        )
    if not isinstance(frozen_identity, FrozenControllerIdentity):
        raise TypeError(
            f"frozen_identity must be FrozenControllerIdentity, got {type(frozen_identity).__name__}"
        )

    reasons: list[str] = []

    # 1. Controller identity lock (D-W19-01)
    if evidence.controller != frozen_identity.controller:
        reasons.append(
            f"CONTROLLER_IDENTITY_MISMATCH: observed {evidence.controller.value}, "
            f"expected {frozen_identity.controller.value}"
        )

    # 2. Policy/config identity lock (D-W19-01)
    if evidence.policy_version != frozen_identity.policy_version:
        reasons.append(
            f"POLICY_VERSION_MISMATCH: observed {evidence.policy_version}, "
            f"expected {frozen_identity.policy_version}"
        )

    if evidence.config_sha256 != frozen_identity.config_sha256:
        reasons.append(
            f"CONFIG_SHA256_MISMATCH: observed {evidence.config_sha256}, "
            f"expected {frozen_identity.config_sha256}"
        )

    # 3. Action and failure behavior locks (D-W19-01 / D-W19-02)
    if evidence.action_profile != frozen_identity.action_profile:
        reasons.append(
            f"ACTION_PROFILE_MISMATCH: observed {evidence.action_profile}, "
            f"expected {frozen_identity.action_profile}"
        )

    if evidence.failure_policy != frozen_identity.failure_policy:
        reasons.append(
            f"FAILURE_POLICY_MISMATCH: observed {evidence.failure_policy}, "
            f"expected {frozen_identity.failure_policy}"
        )

    # 4. Adaptive tuning detection (D-W19-02)
    if evidence.tuning_changed:
        reasons.append("ADAPTIVE_TUNING_DETECTED")

    # 5. Duplicate logical commands (D-W19-03)
    if evidence.duplicate_logical_command:
        reasons.append("DUPLICATE_LOGICAL_COMMAND_DETECTED")

    # 6. Verification state sanity (D-W19-03)
    if not evidence.verification_sensible:
        reasons.append("NONSENSICAL_VERIFICATION_STATE")

    # 7. Control anomalies (D-W19-04)
    if evidence.control_anomaly:
        reasons.append("CONTROL_ANOMALY_DETECTED")

    status = (
        CampaignAssessmentStatus.FLAGGED
        if reasons
        else CampaignAssessmentStatus.ACCEPTED
    )

    reasons_tuple = tuple(reasons)

    ledger_record = PairLedgerRecord(
        pair_id=evidence.pair_id,
        run_id=evidence.run_id,
        controller=evidence.controller,
        policy_version=evidence.policy_version,
        config_sha256=evidence.config_sha256,
        action_profile=evidence.action_profile,
        failure_policy=evidence.failure_policy,
        assessment_status=status,
        flagged_reasons=reasons_tuple,
        silently_corrected=False,
    )

    return CampaignAssessmentDecision(
        status=status,
        reasons=reasons_tuple,
        ledger_record=ledger_record,
        physical_command_emitted=False,
        silently_corrected=False,
    )


def assess_campaign_pair(
    run_a: RunEvidence,
    run_b: RunEvidence,
    frozen_a: FrozenControllerIdentity,
    frozen_b: FrozenControllerIdentity,
) -> PairedCampaignDecision:
    """Assess a matched Controller A/B run pair for Member B's pair ledger.

    Pure function: verifies pair_id match, controller arm designations (A and B),
    evaluates both runs independently, and constructs an immutable paired record.
    """
    if not isinstance(run_a, RunEvidence):
        raise TypeError(f"run_a must be RunEvidence, got {type(run_a).__name__}")
    if not isinstance(run_b, RunEvidence):
        raise TypeError(f"run_b must be RunEvidence, got {type(run_b).__name__}")
    if not isinstance(frozen_a, FrozenControllerIdentity):
        raise TypeError(
            f"frozen_a must be FrozenControllerIdentity, got {type(frozen_a).__name__}"
        )
    if not isinstance(frozen_b, FrozenControllerIdentity):
        raise TypeError(
            f"frozen_b must be FrozenControllerIdentity, got {type(frozen_b).__name__}"
        )

    pair_reasons: list[str] = []

    if run_a.pair_id is None or not run_a.pair_id.strip():
        pair_reasons.append("MISSING_PAIR_ID_RUN_A")
    if run_b.pair_id is None or not run_b.pair_id.strip():
        pair_reasons.append("MISSING_PAIR_ID_RUN_B")

    if (
        run_a.pair_id is not None
        and run_b.pair_id is not None
        and run_a.pair_id != run_b.pair_id
    ):
        pair_reasons.append(
            f"PAIR_ID_MISMATCH: run_a has {run_a.pair_id}, run_b has {run_b.pair_id}"
        )

    if run_a.controller != ControllerVariant.A:
        pair_reasons.append(
            f"EXPECTED_CONTROLLER_A_FOR_ARM_A: got {run_a.controller.value}"
        )
    if run_b.controller != ControllerVariant.B:
        pair_reasons.append(
            f"EXPECTED_CONTROLLER_B_FOR_ARM_B: got {run_b.controller.value}"
        )

    decision_a = assess_campaign_run(run_a, frozen_a)
    decision_b = assess_campaign_run(run_b, frozen_b)

    if decision_a.status == CampaignAssessmentStatus.FLAGGED:
        for r in decision_a.reasons:
            pair_reasons.append(f"RUN_A_FLAGGED: {r}")

    if decision_b.status == CampaignAssessmentStatus.FLAGGED:
        for r in decision_b.reasons:
            pair_reasons.append(f"RUN_B_FLAGGED: {r}")

    effective_pair_id = run_a.pair_id if run_a.pair_id is not None else ""
    pair_status = (
        CampaignAssessmentStatus.FLAGGED
        if pair_reasons
        else CampaignAssessmentStatus.ACCEPTED
    )
    pair_reasons_tuple = tuple(pair_reasons)

    record = PairedCampaignRecord(
        pair_id=effective_pair_id,
        run_a=decision_a.ledger_record,
        run_b=decision_b.ledger_record,
        pair_status=pair_status,
        pair_reasons=pair_reasons_tuple,
        silently_corrected=False,
    )

    return PairedCampaignDecision(
        pair_status=pair_status,
        pair_reasons=pair_reasons_tuple,
        record=record,
        physical_command_emitted=False,
        silently_corrected=False,
    )
