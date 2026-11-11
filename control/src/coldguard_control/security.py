"""Pure W15 authorization boundary used before command validation.

Authentication, broker ACL enforcement and TLS remain transport concerns.
This module consumes their asserted result and applies explicit role/device
scope without owning credentials or secrets.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CommandRole(str, Enum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    EXPERIMENTER = "EXPERIMENTER"
    ADMIN = "ADMIN"


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
