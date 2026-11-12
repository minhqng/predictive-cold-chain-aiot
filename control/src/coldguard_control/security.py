"""Pure W15 authorization boundary and security readiness assessment.

Authentication, broker ACL enforcement and TLS remain transport concerns.
This module consumes their asserted result and applies explicit role/device
scope without owning credentials or secrets.

W15 Security Readiness Assessment covers:
- Broker ACL contract (publish/subscribe permissions)
- Unauthorized publish denied + no actuation
- Secret/log scan clean (no credentials in logs)
- Insufficient backend role denial
- Trusted/invalid TLS endpoint plan/results
- Host vs live evidence distinction
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CommandRole(str, Enum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    EXPERIMENTER = "EXPERIMENTER"
    ADMIN = "ADMIN"


class SecurityReadinessStatus(str, Enum):
    NOT_ASSESSED = "NOT_ASSESSED"
    HOST_SIMULATED = "HOST_SIMULATED"
    LIVE_VALIDATED = "LIVE_VALIDATED"


class TLSEndpointStatus(str, Enum):
    TRUSTED = "TRUSTED"
    INVALID = "INVALID"
    NOT_TESTED = "NOT_TESTED"


@dataclass(frozen=True, slots=True)
class BrokerACLContract:
    """W15 broker ACL contract specification.

    Documents the expected publish/subscribe permissions and verifies
    unauthorized publish attempts are denied with no actuation.
    """
    allowed_publish_topics: tuple[str, ...]
    allowed_subscribe_topics: tuple[str, ...]
    unauthorized_publish_denied: bool  # Must be True for readiness
    no_actuation_on_denial: bool  # Must be True - denial prevents physical action
    acl_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.acl_version, str) or not self.acl_version.strip():
            raise ValueError("acl_version must be non-empty string")
        if not isinstance(self.allowed_publish_topics, tuple) or not self.allowed_publish_topics or not all(
            isinstance(t, str) and t.strip() for t in self.allowed_publish_topics
        ):
            raise ValueError("allowed_publish_topics must be tuple of non-empty strings")
        if not isinstance(self.allowed_subscribe_topics, tuple) or not self.allowed_subscribe_topics or not all(
            isinstance(t, str) and t.strip() for t in self.allowed_subscribe_topics
        ):
            raise ValueError("allowed_subscribe_topics must be tuple of non-empty strings")
        if not isinstance(self.unauthorized_publish_denied, bool):
            raise ValueError("unauthorized_publish_denied must be boolean")
        if not isinstance(self.no_actuation_on_denial, bool):
            raise ValueError("no_actuation_on_denial must be boolean")


@dataclass(frozen=True, slots=True)
class SecretScanResult:
    """W15 secret/log scan results.

    Verifies no credentials, tokens, or secrets appear in logs or telemetry.
    """
    scan_tool: str
    paths_scanned: tuple[str, ...]
    secrets_found: int  # Must be 0 for readiness
    log_scan_clean: bool  # Must be True - no secrets in logs
    scan_timestamp: str  # ISO 8601 timestamp

    def __post_init__(self) -> None:
        if not isinstance(self.scan_tool, str) or not self.scan_tool.strip():
            raise ValueError("scan_tool must be non-empty string")
        if not isinstance(self.paths_scanned, tuple) or not self.paths_scanned or not all(
            isinstance(p, str) and p.strip() for p in self.paths_scanned
        ):
            raise ValueError("paths_scanned must be tuple of non-empty strings")
        if isinstance(self.secrets_found, bool) or not isinstance(self.secrets_found, int) or self.secrets_found < 0:
            raise ValueError("secrets_found must be non-negative integer")
        if not isinstance(self.log_scan_clean, bool):
            raise ValueError("log_scan_clean must be boolean")
        if not isinstance(self.scan_timestamp, str) or not self.scan_timestamp.strip():
            raise ValueError("scan_timestamp must be non-empty string")


@dataclass(frozen=True, slots=True)
class RoleDenialTest:
    """W15 insufficient backend role denial test.

    Verifies that roles without sufficient permissions are denied.
    """
    tested_role: CommandRole
    attempted_action: str
    denial_expected: bool
    denial_observed: bool  # Must be True for readiness
    denial_reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.tested_role, CommandRole):
            raise ValueError("tested_role must be CommandRole")
        if not isinstance(self.attempted_action, str) or not self.attempted_action.strip():
            raise ValueError("attempted_action must be non-empty string")
        if not isinstance(self.denial_expected, bool):
            raise ValueError("denial_expected must be boolean")
        if not isinstance(self.denial_observed, bool):
            raise ValueError("denial_observed must be boolean")
        if not isinstance(self.denial_reason_code, str) or not self.denial_reason_code.strip():
            raise ValueError("denial_reason_code must be non-empty string")


@dataclass(frozen=True, slots=True)
class TLSEndpointTest:
    """W15 trusted/invalid TLS endpoint test results.

    Documents TLS endpoint validation including both trusted and invalid
    certificate handling. Distinguishes host simulation from live testing.
    """
    endpoint_url: str
    expected_status: TLSEndpointStatus
    observed_status: TLSEndpointStatus
    certificate_validated: bool
    authority: SecurityReadinessStatus  # HOST_SIMULATED or LIVE_VALIDATED

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint_url, str) or not self.endpoint_url.strip():
            raise ValueError("endpoint_url must be non-empty string")
        if not isinstance(self.expected_status, TLSEndpointStatus):
            raise ValueError("expected_status must be TLSEndpointStatus")
        if not isinstance(self.observed_status, TLSEndpointStatus):
            raise ValueError("observed_status must be TLSEndpointStatus")
        if not isinstance(self.certificate_validated, bool):
            raise ValueError("certificate_validated must be boolean")
        if not isinstance(self.authority, SecurityReadinessStatus):
            raise ValueError("authority must be SecurityReadinessStatus")


@dataclass(frozen=True, slots=True)
class SecurityReadinessEvidence:
    """W15 security readiness assessment evidence.

    Aggregates all security readiness components with explicit host vs live
    distinction.
    """
    broker_acl_contract: BrokerACLContract
    secret_scan_result: SecretScanResult
    role_denial_tests: tuple[RoleDenialTest, ...]
    tls_endpoint_tests: tuple[TLSEndpointTest, ...]
    authority: SecurityReadinessStatus
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.broker_acl_contract, BrokerACLContract):
            raise ValueError("broker_acl_contract must be BrokerACLContract")
        if not isinstance(self.secret_scan_result, SecretScanResult):
            raise ValueError("secret_scan_result must be SecretScanResult")
        if not isinstance(self.role_denial_tests, tuple) or len(self.role_denial_tests) == 0:
            raise ValueError("role_denial_tests must be non-empty tuple")
        if not all(isinstance(t, RoleDenialTest) for t in self.role_denial_tests):
            raise ValueError("all role_denial_tests must be RoleDenialTest")
        if not isinstance(self.tls_endpoint_tests, tuple) or len(self.tls_endpoint_tests) == 0:
            raise ValueError("tls_endpoint_tests must be non-empty tuple")
        if not all(isinstance(t, TLSEndpointTest) for t in self.tls_endpoint_tests):
            raise ValueError("all tls_endpoint_tests must be TLSEndpointTest")
        if not isinstance(self.authority, SecurityReadinessStatus):
            raise ValueError("authority must be SecurityReadinessStatus")
        if self.evidence_reference is not None and (
            not isinstance(self.evidence_reference, str)
            or not self.evidence_reference.strip()
        ):
            raise ValueError("evidence_reference must be non-empty when provided")
        if (
            self.authority is SecurityReadinessStatus.LIVE_VALIDATED
            and self.evidence_reference is None
        ):
            raise ValueError("LIVE_VALIDATED requires evidence_reference")


@dataclass(frozen=True, slots=True)
class SecurityReadinessDecision:
    ready: bool
    blockers: tuple[str, ...]
    authority: SecurityReadinessStatus
    host_simulation_valid: bool
    live_validation_complete: bool


def assess_security_readiness(
    evidence: SecurityReadinessEvidence,
) -> SecurityReadinessDecision:
    """Assess W15 security readiness.

    W15 requirements:
    - Broker ACL contract with unauthorized publish denied + no actuation
    - Secret/log scan clean (0 secrets found)
    - Role denial tests all observed denial
    - TLS endpoint tests with explicit authority
    - Host vs live distinction
    """
    if not isinstance(evidence, SecurityReadinessEvidence):
        raise ValueError("evidence must be SecurityReadinessEvidence")

    blockers: list[str] = []

    # Broker ACL contract checks
    acl = evidence.broker_acl_contract
    if not acl.unauthorized_publish_denied:
        blockers.append("unauthorized_publish_not_denied")
    if not acl.no_actuation_on_denial:
        blockers.append("actuation_occurred_on_acl_denial")

    # Secret scan checks
    scan = evidence.secret_scan_result
    if scan.secrets_found != 0:
        blockers.append("secrets_found_in_scan")
    if not scan.log_scan_clean:
        blockers.append("secrets_in_logs")

    # Role denial tests
    for i, test in enumerate(evidence.role_denial_tests):
        if not test.denial_expected or not test.denial_observed:
            blockers.append(f"role_denial_test_{i}_not_denied")

    # TLS endpoint tests
    for i, test in enumerate(evidence.tls_endpoint_tests):
        if test.observed_status != test.expected_status:
            blockers.append(f"tls_test_{i}_status_mismatch")
        if (
            test.expected_status is TLSEndpointStatus.TRUSTED
            and not test.certificate_validated
        ):
            blockers.append(f"tls_test_{i}_trusted_certificate_not_validated")
        if (
            test.expected_status is TLSEndpointStatus.INVALID
            and test.certificate_validated
        ):
            blockers.append(f"tls_test_{i}_invalid_certificate_accepted")
        if test.authority is not evidence.authority:
            blockers.append(f"tls_test_{i}_authority_mismatch")

    expected_tls_statuses = {test.expected_status for test in evidence.tls_endpoint_tests}
    if TLSEndpointStatus.TRUSTED not in expected_tls_statuses:
        blockers.append("trusted_tls_endpoint_not_tested")
    if TLSEndpointStatus.INVALID not in expected_tls_statuses:
        blockers.append("invalid_tls_endpoint_not_tested")

    core_valid = not blockers
    host_simulation_valid = (
        evidence.authority is SecurityReadinessStatus.HOST_SIMULATED and core_valid
    )
    live_validation_complete = (
        evidence.authority is SecurityReadinessStatus.LIVE_VALIDATED and core_valid
    )

    if not live_validation_complete:
        blockers.append("live_validation_required")

    ready = live_validation_complete

    return SecurityReadinessDecision(
        ready=ready,
        blockers=tuple(blockers),
        authority=evidence.authority,
        host_simulation_valid=host_simulation_valid,
        live_validation_complete=live_validation_complete,
    )


@dataclass(frozen=True, slots=True)
class CommandAuthorizationInput:
    authenticated: bool
    role: CommandRole
    requested_device_id: str
    scoped_device_ids: frozenset[str]
    command_roles: frozenset[CommandRole]
    durable_audit_available: bool
    predictive_command: bool

    def __post_init__(self) -> None:
        for name in ("authenticated", "durable_audit_available", "predictive_command"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        if not isinstance(self.role, CommandRole):
            raise ValueError("role must be CommandRole")
        if not isinstance(self.requested_device_id, str) or not self.requested_device_id.strip():
            raise ValueError("requested_device_id must be non-empty")
        if not isinstance(self.scoped_device_ids, frozenset) or not all(
            isinstance(value, str) and value.strip() for value in self.scoped_device_ids
        ):
            raise ValueError("scoped_device_ids must be a frozenset of device ids")
        if not isinstance(self.command_roles, frozenset) or not all(
            isinstance(value, CommandRole) for value in self.command_roles
        ):
            raise ValueError("command_roles must be a frozenset of CommandRole")
        if CommandRole.VIEWER in self.command_roles:
            raise ValueError("VIEWER must remain read-only")


@dataclass(frozen=True, slots=True)
class CommandAuthorizationDecision:
    allowed: bool
    reason: str


def authorize_command(
    request: CommandAuthorizationInput,
) -> CommandAuthorizationDecision:
    """Apply authn, role, device-scope and durable-audit checks in order."""
    if not isinstance(request, CommandAuthorizationInput):
        raise ValueError("request must be CommandAuthorizationInput")
    if not request.authenticated:
        return CommandAuthorizationDecision(False, "AUTHENTICATION_FAILED")
    if request.role not in request.command_roles:
        return CommandAuthorizationDecision(False, "ROLE_NOT_AUTHORIZED")
    if request.requested_device_id not in request.scoped_device_ids:
        return CommandAuthorizationDecision(False, "DEVICE_OUT_OF_SCOPE")
    if request.predictive_command and not request.durable_audit_available:
        return CommandAuthorizationDecision(False, "DURABLE_AUDIT_UNAVAILABLE")
    return CommandAuthorizationDecision(True, "AUTHORIZED")
