"""Strict projection of Member C's v0 wire command into D's pure validator.

This only prepares an input for ``validate_command``. Authentication, MQTT
delivery, device parsing and actuation remain separate integration gates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from coldguard_control.commands import CommandRequest, CommandSchemaError, SUPPORTED_SCHEMA_VERSION
from coldguard_control.types import CoolingState


def _utc_seconds(value: object, name: str) -> float:
    if not isinstance(value, str):
        raise CommandSchemaError(f"{name} must be an ISO-8601 UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CommandSchemaError(f"{name} must be an ISO-8601 UTC string") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise CommandSchemaError(f"{name} must specify UTC")
    return parsed.timestamp()


def project_canonical_command(
    payload: Mapping[str, object], *, authorized: bool, retain: bool = False
) -> CommandRequest:
    """Reject missing C provenance before constructing D's reduced request."""
    if not isinstance(payload, Mapping):
        raise CommandSchemaError("command payload must be a mapping")
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != SUPPORTED_SCHEMA_VERSION:
        raise CommandSchemaError("unsupported schema_version")
    for name in ("command_id", "device_id", "controller_id", "policy_version", "reason_code"):
        if not isinstance(payload.get(name), str) or not payload[name].strip():
            raise CommandSchemaError(f"{name} is required by the C command contract")
    action = payload.get("action")
    if not isinstance(action, Mapping):
        raise CommandSchemaError("action must be a mapping")
    cooling = action.get("cooling")
    if cooling not in ("ON", "OFF") or type(cooling) is not str:
        raise CommandSchemaError("action.cooling must be ON or OFF")
    duty = action.get("duty")
    if duty is not None and (type(duty) not in (int, float)):
        raise CommandSchemaError("action.duty must be numeric or absent")
    created = _utc_seconds(payload.get("created_at"), "created_at")
    expires = _utc_seconds(payload.get("expires_at"), "expires_at")
    if expires <= created:
        raise CommandSchemaError("expires_at must be later than created_at")
    if type(authorized) is not bool or type(retain) is not bool:
        raise CommandSchemaError("authorized and retain must be booleans")
    return CommandRequest(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        command_id=payload["command_id"],
        device_id=payload["device_id"],
        action=CoolingState(cooling),
        created_at=created,
        expires_at=expires,
        authorized=authorized,
        duty=duty,
        retain=retain,
    )
