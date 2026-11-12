from coldguard_control.security import (
    CommandAuthorizationInput,
    CommandRole,
    authorize_command,
)
import pytest


def request(**overrides):
    values = {
        "authenticated": True,
        "role": CommandRole.OPERATOR,
        "requested_device_id": "cg-001",
        "scoped_device_ids": frozenset({"cg-001"}),
        "command_roles": frozenset({CommandRole.OPERATOR, CommandRole.ADMIN}),
        "durable_audit_available": True,
        "predictive_command": False,
    }
    values.update(overrides)
    return CommandAuthorizationInput(**values)


def test_viewer_is_separated_from_command_roles():
    decision = authorize_command(request(role=CommandRole.VIEWER))
    assert decision.allowed is False
    assert decision.reason == "ROLE_NOT_AUTHORIZED"


def test_device_scope_is_exact():
    decision = authorize_command(request(requested_device_id="cg-002"))
    assert decision.allowed is False
    assert decision.reason == "DEVICE_OUT_OF_SCOPE"


def test_predictive_command_requires_durable_audit():
    decision = authorize_command(request(
        predictive_command=True, durable_audit_available=False
    ))
    assert decision.allowed is False
    assert decision.reason == "DURABLE_AUDIT_UNAVAILABLE"


def test_authorized_operator_is_admitted_to_next_safety_layer():
    assert authorize_command(request()).allowed is True


def test_viewer_cannot_be_misconfigured_as_command_role():
    with pytest.raises(ValueError, match="read-only"):
        request(command_roles=frozenset({CommandRole.VIEWER}))
