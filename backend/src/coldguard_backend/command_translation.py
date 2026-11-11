"""Translate the canonical backend command envelope into the device record.

Member C publishes the Doc 02 section 28.1 JSON envelope (``Command``); the
Member A device consumes a flat space-separated ``key=value`` record over the
unit-explicit names in ``firmware/main/cg_command.c`` (W06 handoff section 6.2
item 2; evidence/A/HANDOFF/member-a-bcd-contract.json ``command_surface``).
That translation is the serial gateway's responsibility and was an open
contract item with no implementation in any member PR. This module supplies the
bounded W06/W13 prerequisite so the existing producer and consumer can be
integration-tested against one another.

Authority and limits:
- The field-name set stays 1:1 with Doc 02 section 28.1; optional envelope
  fields the device does not accept (prediction_id / run_id /
  expected_twin_version) are dropped, never renamed into unknown keys.
- ``created_at`` / ``expires_at`` are converted faithfully from the backend's
  trusted UTC to epoch milliseconds. This does NOT establish device clock
  synchronization: the device's own EPOCH_UNSYNCHRONIZED safety gate
  (cg_command.c) remains the fail-closed authority for remote actuation
  (W06 handoff section 6.2 item 1, still open).
- Action range / expiry / local safety validation stays on the device
  (Doc 02 section 29: backend authorization does not replace device
  validation). This module only guarantees a well-formed device record.
"""

from __future__ import annotations

from datetime import datetime

from .contracts import Command

# Exactly the ten names at firmware/main/cg_command.c:559-561, in record order.
DEVICE_COMMAND_FIELDS = (
    "schema_version",
    "command_id",
    "device_id",
    "created_at_ms",
    "expires_at_ms",
    "controller_id",
    "policy_version",
    "reason_code",
    "action_cooling",
    "action_duty_permille",
)

# CG_COMMAND_RECORD_MAX=512 (firmware/main/cg_command.h:78);
# CG_CMD_FIELDS_MAX=24 key=value tokens (firmware/main/cg_command.c:13).
CG_COMMAND_RECORD_MAX = 512
CG_CMD_FIELDS_MAX = 24


class CommandTranslationError(ValueError):
    """The envelope cannot be rendered as a well-formed device record."""


def _epoch_ms(value: datetime) -> int:
    if value.tzinfo is None:
        raise CommandTranslationError(
            "NAIVE_TIMESTAMP: backend command time must be timezone-aware UTC; "
            "refusing to invent a timezone for epoch conversion"
        )
    return int(value.timestamp() * 1000)


def command_to_device_fields(command: Command) -> dict[str, object]:
    """Map the envelope to the flat device field set (no optional extras)."""
    action = command.action
    duty = action.duty if action.duty is not None else 0.0
    return {
        "schema_version": int(command.schema_version),
        "command_id": command.command_id,
        "device_id": command.device_id,
        "created_at_ms": _epoch_ms(command.created_at),
        "expires_at_ms": _epoch_ms(command.expires_at),
        "controller_id": command.controller_id,
        "policy_version": command.policy_version,
        "reason_code": command.reason_code,
        "action_cooling": action.cooling,
        "action_duty_permille": int(round(duty * 1000)),
    }


def translate_command_to_device_serial(command: Command) -> str:
    """Render ``command`` as the device ``key=value`` record.

    Raises CommandTranslationError if the record would violate the device
    encoding contract (unknown/missing key, oversize, too many tokens). The
    device still performs its own admission and safety checks on the result.
    """
    fields = command_to_device_fields(command)
    if set(fields) != set(DEVICE_COMMAND_FIELDS):
        raise CommandTranslationError("FIELD_SET_MISMATCH: device names must stay 1:1")
    tokens = [f"{name}={fields[name]}" for name in DEVICE_COMMAND_FIELDS]
    for token in tokens:
        key, _, value = token.partition("=")
        if not value or " " in value or "=" in value:
            raise CommandTranslationError(
                f"INVALID_TOKEN: {key!r} must be a single non-empty key=value token"
            )
    record = " ".join(tokens)
    if len(tokens) > CG_CMD_FIELDS_MAX:
        raise CommandTranslationError("TOO_MANY_TOKENS")
    if len(record.encode("ascii")) > CG_COMMAND_RECORD_MAX:
        raise CommandTranslationError("RECORD_TOO_LONG")
    return record