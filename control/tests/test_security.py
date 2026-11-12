"""W15 security readiness assessment tests."""
import pytest

from coldguard_control.security import (
    BrokerACLContract,
    CommandAuthorizationInput,
    CommandAuthorizationDecision,
    CommandRole,
    RoleDenialTest,
    SecretScanResult,
    SecurityReadinessDecision,
    SecurityReadinessEvidence,
    SecurityReadinessStatus,
    TLSEndpointStatus,
    TLSEndpointTest,
    assess_security_readiness,
    authorize_command,
)


def test_broker_acl_contract_validation():
    acl = BrokerACLContract(
        allowed_publish_topics=("device/+/command",),
        allowed_subscribe_topics=("device/+/status",),
        unauthorized_publish_denied=True,
        no_actuation_on_denial=True,
        acl_version="v1.0",
    )
    assert acl.unauthorized_publish_denied is True
    assert acl.no_actuation_on_denial is True

    with pytest.raises(ValueError, match="unauthorized_publish_denied"):
        BrokerACLContract(
            allowed_publish_topics=("device/+/command",),
            allowed_subscribe_topics=("device/+/status",),
            unauthorized_publish_denied="yes",  # type: ignore
            no_actuation_on_denial=True,
            acl_version="v1.0",
        )


def test_secret_scan_result_validation():
    scan = SecretScanResult(
        scan_tool="gitleaks",
        paths_scanned=("src/", "tests/"),
        secrets_found=0,
        log_scan_clean=True,
        scan_timestamp="2026-11-12T10:00:00Z",
    )
    assert scan.secrets_found == 0
    assert scan.log_scan_clean is True

    with pytest.raises(ValueError, match="secrets_found"):
        SecretScanResult(
            scan_tool="gitleaks",
            paths_scanned=("src/",),
            secrets_found=-1,
            log_scan_clean=True,
            scan_timestamp="2026-11-12T10:00:00Z",
        )


def test_role_denial_test_validation():
    test = RoleDenialTest(
        tested_role=CommandRole.VIEWER,
        attempted_action="PUBLISH_COMMAND",
        denial_expected=True,
        denial_observed=True,
        denial_reason_code="ROLE_NOT_AUTHORIZED",
    )
    assert test.denial_observed is True


def test_tls_endpoint_test_validation():
    test = TLSEndpointTest(
        endpoint_url="https://api.example.com",
        expected_status=TLSEndpointStatus.TRUSTED,
        observed_status=TLSEndpointStatus.TRUSTED,
        certificate_validated=True,
        authority=SecurityReadinessStatus.HOST_SIMULATED,
    )
    assert test.authority is SecurityReadinessStatus.HOST_SIMULATED


def test_security_readiness_evidence_validation():
    acl = BrokerACLContract(
        allowed_publish_topics=("device/+/command",),
        allowed_subscribe_topics=("device/+/status",),
        unauthorized_publish_denied=True,
        no_actuation_on_denial=True,
        acl_version="v1.0",
    )
    scan = SecretScanResult(
        scan_tool="gitleaks",
        paths_scanned=("src/",),
        secrets_found=0,
        log_scan_clean=True,
        scan_timestamp="2026-11-12T10:00:00Z",
    )
    role_test = RoleDenialTest(
        tested_role=CommandRole.VIEWER,
        attempted_action="PUBLISH_COMMAND",
        denial_expected=True,
        denial_observed=True,
        denial_reason_code="ROLE_NOT_AUTHORIZED",
    )
    tls_test = TLSEndpointTest(
        endpoint_url="https://api.example.com",
        expected_status=TLSEndpointStatus.TRUSTED,
        observed_status=TLSEndpointStatus.TRUSTED,
        certificate_validated=True,
        authority=SecurityReadinessStatus.HOST_SIMULATED,
    )

    evidence = SecurityReadinessEvidence(
        broker_acl_contract=acl,
        secret_scan_result=scan,
        role_denial_tests=(role_test,),
        tls_endpoint_tests=(tls_test,),
        authority=SecurityReadinessStatus.HOST_SIMULATED,
    )
    assert evidence.authority is SecurityReadinessStatus.HOST_SIMULATED


def test_assess_security_readiness_host_simulated_pass():
    acl = BrokerACLContract(
        allowed_publish_topics=("device/+/command",),
        allowed_subscribe_topics=("device/+/status",),
        unauthorized_publish_denied=True,
        no_actuation_on_denial=True,
        acl_version="v1.0",
    )
    scan = SecretScanResult(
        scan_tool="gitleaks",
        paths_scanned=("src/",),
        secrets_found=0,
        log_scan_clean=True,
        scan_timestamp="2026-11-12T10:00:00Z",
    )
    role_test = RoleDenialTest(
        tested_role=CommandRole.VIEWER,
        attempted_action="PUBLISH_COMMAND",
        denial_expected=True,
        denial_observed=True,
        denial_reason_code="ROLE_NOT_AUTHORIZED",
    )
    tls_test = TLSEndpointTest(
        endpoint_url="https://api.example.com",
        expected_status=TLSEndpointStatus.TRUSTED,
        observed_status=TLSEndpointStatus.TRUSTED,
        certificate_validated=True,
        authority=SecurityReadinessStatus.HOST_SIMULATED,
    )
    invalid_tls_test = TLSEndpointTest(
        endpoint_url="https://invalid.example.com",
        expected_status=TLSEndpointStatus.INVALID,
        observed_status=TLSEndpointStatus.INVALID,
        certificate_validated=False,
        authority=SecurityReadinessStatus.HOST_SIMULATED,
    )

    evidence = SecurityReadinessEvidence(
        broker_acl_contract=acl,
        secret_scan_result=scan,
        role_denial_tests=(role_test,),
        tls_endpoint_tests=(tls_test, invalid_tls_test),
        authority=SecurityReadinessStatus.HOST_SIMULATED,
    )

    result = assess_security_readiness(evidence)
    assert result.ready is False
    assert "live_validation_required" in result.blockers
    assert result.authority is SecurityReadinessStatus.HOST_SIMULATED
    assert result.host_simulation_valid is True
    assert result.live_validation_complete is False


def test_assess_security_readiness_unauthorized_publish_not_denied():
    acl = BrokerACLContract(
        allowed_publish_topics=("device/+/command",),
        allowed_subscribe_topics=("device/+/status",),
        unauthorized_publish_denied=False,  # FAIL
        no_actuation_on_denial=True,
        acl_version="v1.0",
    )
    scan = SecretScanResult(
        scan_tool="gitleaks",
        paths_scanned=("src/",),
        secrets_found=0,
        log_scan_clean=True,
        scan_timestamp="2026-11-12T10:00:00Z",
    )
    role_test = RoleDenialTest(
        tested_role=CommandRole.VIEWER,
        attempted_action="PUBLISH_COMMAND",
        denial_expected=True,
        denial_observed=True,
        denial_reason_code="ROLE_NOT_AUTHORIZED",
    )
    tls_test = TLSEndpointTest(
        endpoint_url="https://api.example.com",
        expected_status=TLSEndpointStatus.TRUSTED,
        observed_status=TLSEndpointStatus.TRUSTED,
        certificate_validated=True,
        authority=SecurityReadinessStatus.HOST_SIMULATED,
    )

    evidence = SecurityReadinessEvidence(
        broker_acl_contract=acl,
        secret_scan_result=scan,
        role_denial_tests=(role_test,),
        tls_endpoint_tests=(tls_test,),
        authority=SecurityReadinessStatus.HOST_SIMULATED,
    )

    result = assess_security_readiness(evidence)
    assert result.ready is False
    assert "unauthorized_publish_not_denied" in result.blockers


def test_assess_security_readiness_secrets_found():
    acl = BrokerACLContract(
        allowed_publish_topics=("device/+/command",),
        allowed_subscribe_topics=("device/+/status",),
        unauthorized_publish_denied=True,
        no_actuation_on_denial=True,
        acl_version="v1.0",
    )
    scan = SecretScanResult(
        scan_tool="gitleaks",
        paths_scanned=("src/",),
        secrets_found=3,  # FAIL - secrets found
        log_scan_clean=False,
        scan_timestamp="2026-11-12T10:00:00Z",
    )
    role_test = RoleDenialTest(
        tested_role=CommandRole.VIEWER,
        attempted_action="PUBLISH_COMMAND",
        denial_expected=True,
        denial_observed=True,
        denial_reason_code="ROLE_NOT_AUTHORIZED",
    )
    tls_test = TLSEndpointTest(
        endpoint_url="https://api.example.com",
        expected_status=TLSEndpointStatus.TRUSTED,
        observed_status=TLSEndpointStatus.TRUSTED,
        certificate_validated=True,
        authority=SecurityReadinessStatus.HOST_SIMULATED,
    )

    evidence = SecurityReadinessEvidence(
        broker_acl_contract=acl,
        secret_scan_result=scan,
        role_denial_tests=(role_test,),
        tls_endpoint_tests=(tls_test,),
        authority=SecurityReadinessStatus.HOST_SIMULATED,
    )

    result = assess_security_readiness(evidence)
    assert result.ready is False
    assert "secrets_found_in_scan" in result.blockers
    assert "secrets_in_logs" in result.blockers


def test_assess_security_readiness_live_validated():
    acl = BrokerACLContract(
        allowed_publish_topics=("device/+/command",),
        allowed_subscribe_topics=("device/+/status",),
        unauthorized_publish_denied=True,
        no_actuation_on_denial=True,
        acl_version="v1.0",
    )
    scan = SecretScanResult(
        scan_tool="gitleaks",
        paths_scanned=("src/",),
        secrets_found=0,
        log_scan_clean=True,
        scan_timestamp="2026-11-12T10:00:00Z",
    )
    role_test = RoleDenialTest(
        tested_role=CommandRole.VIEWER,
        attempted_action="PUBLISH_COMMAND",
        denial_expected=True,
        denial_observed=True,
        denial_reason_code="ROLE_NOT_AUTHORIZED",
    )
    tls_test = TLSEndpointTest(
        endpoint_url="https://api.example.com",
        expected_status=TLSEndpointStatus.TRUSTED,
        observed_status=TLSEndpointStatus.TRUSTED,
        certificate_validated=True,
        authority=SecurityReadinessStatus.LIVE_VALIDATED,
    )
    invalid_tls_test = TLSEndpointTest(
        endpoint_url="https://invalid.example.com",
        expected_status=TLSEndpointStatus.INVALID,
        observed_status=TLSEndpointStatus.INVALID,
        certificate_validated=False,
        authority=SecurityReadinessStatus.LIVE_VALIDATED,
    )

    evidence = SecurityReadinessEvidence(
        broker_acl_contract=acl,
        secret_scan_result=scan,
        role_denial_tests=(role_test,),
        tls_endpoint_tests=(tls_test, invalid_tls_test),
        authority=SecurityReadinessStatus.LIVE_VALIDATED,
        evidence_reference="evidence/D/W15/live-security.json",
    )

    result = assess_security_readiness(evidence)
    assert result.ready is True
    assert result.authority is SecurityReadinessStatus.LIVE_VALIDATED
    assert result.host_simulation_valid is False
    assert result.live_validation_complete is True


def test_authorize_command_basic():
    request = CommandAuthorizationInput(
        authenticated=True,
        role=CommandRole.OPERATOR,
        requested_device_id="device-001",
        scoped_device_ids=frozenset(["device-001", "device-002"]),
        command_roles=frozenset([CommandRole.OPERATOR, CommandRole.EXPERIMENTER]),
        durable_audit_available=True,
        predictive_command=False,
    )
    result = authorize_command(request)
    assert result.allowed is True
    assert result.reason == "AUTHORIZED"


def test_authorize_command_unauthenticated():
    request = CommandAuthorizationInput(
        authenticated=False,
        role=CommandRole.OPERATOR,
        requested_device_id="device-001",
        scoped_device_ids=frozenset(["device-001"]),
        command_roles=frozenset([CommandRole.OPERATOR]),
        durable_audit_available=True,
        predictive_command=False,
    )
    result = authorize_command(request)
    assert result.allowed is False
    assert result.reason == "AUTHENTICATION_FAILED"


def test_authorize_command_role_not_authorized():
    request = CommandAuthorizationInput(
        authenticated=True,
        role=CommandRole.VIEWER,
        requested_device_id="device-001",
        scoped_device_ids=frozenset(["device-001"]),
        command_roles=frozenset([CommandRole.OPERATOR]),
        durable_audit_available=True,
        predictive_command=False,
    )
    result = authorize_command(request)
    assert result.allowed is False
    assert result.reason == "ROLE_NOT_AUTHORIZED"


def test_authorize_command_device_out_of_scope():
    request = CommandAuthorizationInput(
        authenticated=True,
        role=CommandRole.OPERATOR,
        requested_device_id="device-003",
        scoped_device_ids=frozenset(["device-001", "device-002"]),
        command_roles=frozenset([CommandRole.OPERATOR]),
        durable_audit_available=True,
        predictive_command=False,
    )
    result = authorize_command(request)
    assert result.allowed is False
    assert result.reason == "DEVICE_OUT_OF_SCOPE"


def test_authorize_command_predictive_requires_audit():
    request = CommandAuthorizationInput(
        authenticated=True,
        role=CommandRole.OPERATOR,
        requested_device_id="device-001",
        scoped_device_ids=frozenset(["device-001"]),
        command_roles=frozenset([CommandRole.OPERATOR]),
        durable_audit_available=False,
        predictive_command=True,
    )
    result = authorize_command(request)
    assert result.allowed is False
    assert result.reason == "DURABLE_AUDIT_UNAVAILABLE"
