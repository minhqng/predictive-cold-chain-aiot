"""Translate the Member A device command-ACK into the backend ACK envelope.

The Member A device emits ``#CG CMDACK`` as a flat space-separated ``key=value``
serial record (firmware/main/cg_command.c:448; evidence/A/W06/ack-fixture.json).
Member C's ``ack_consumer`` ingests the Doc 02 section 32.3 ``CommandAck`` JSON
envelope on ``coldguard/{device_id}/command_ack``. The serial gateway
explicitly skips CMDACK records ("have their own contracts", C#69
backend/scripts/serial_gateway.py), so the serial->envelope translation was an
absent bounded prerequisite. This module supplies it, symmetric to
``command_translation`` for the downlink.

Authority and limits:
- The ACK status set is the closed Doc 02 section 32.1 vocabulary (identical to
  firmware/tools/cg_telemetry_schema.ACK_STATUS_VOCABULARY and C CommandAck
  AckStatus); an unknown status fails closed, never coerced.
- ``canonical_status`` carries the original verdict for DUPLICATE_CANONICAL
  (cg_command.c:286); a duplicate without it fails closed.
- ``device_mode`` is passed through as the device's free-string actuator mode
  (e.g. OFF); mapping it into a policy state is Member D's decision, not made
  here.
- No ``ack_time`` is fabricated: the device has no wall clock. Backend receipt
  time belongs to the gateway/consumer, not to this translation.
- The output is the CommandAck JSON shape; Member C's CommandAck model
  (unmerged C#69) remains the validation authority and is not duplicated here.
"""

from __future__ import annotations

# Doc 02 section 32.1 closed ACK verdict set (== A ACK_STATUS_VOCABULARY).
ACK_STATUS_VOCABULARY = (
    "ACCEPTED",
    "REJECTED",
    "DUPLICATE_CANONICAL",
    "EXPIRED",
    "SAFETY_BLOCKED",
    "INVALID_STATE",
    "OUT_OF_RANGE",
)

_DEVICE_ACK_PREFIX = "#CG CMDACK"
_REQUIRED = ("schema", "command_id", "device_id", "boot_id", "status", "reason", "uptime_ms")


class AckTranslationError(ValueError):
    """The device ACK cannot be rendered as a well-formed backend envelope."""


def parse_device_ack_fields(line: str) -> dict[str, str]:
    """Parse the ``#CG CMDACK`` key=value record into a field dict."""
    text = line.strip()
    if not text.startswith(_DEVICE_ACK_PREFIX):
        raise AckTranslationError("NOT_CMDACK: expected a #CG CMDACK record")
    fields: dict[str, str] = {}
    for token in text[len(_DEVICE_ACK_PREFIX):].split():
        key, sep, value = token.partition("=")
        if not sep or not key or not value:
            raise AckTranslationError(f"INVALID_TOKEN: {token!r}")
        if key in fields:
            raise AckTranslationError(f"DUPLICATE_FIELD: {key}")
        fields[key] = value
    missing = [name for name in _REQUIRED if name not in fields]
    if missing:
        raise AckTranslationError(f"MISSING_FIELDS: {', '.join(missing)}")
    return fields


def _bool01(fields: dict[str, str], name: str) -> bool | None:
    if name not in fields:
        return None
    if fields[name] not in ("0", "1"):
        raise AckTranslationError(f"INVALID_BOOL: {name}={fields[name]!r}")
    return fields[name] == "1"


def _int_field(fields: dict[str, str], name: str) -> int:
    try:
        return int(fields[name])
    except (ValueError, TypeError):
        raise AckTranslationError(f"INVALID_INT: {name}={fields[name]!r}") from None


def _action(fields: dict[str, str], cooling_key: str, duty_key: str) -> dict | None:
    if cooling_key not in fields:
        return None
    cooling = fields[cooling_key]
    if cooling not in ("ON", "OFF"):
        raise AckTranslationError(f"INVALID_COOLING: {cooling_key}={cooling!r}")
    action: dict = {"cooling": cooling}
    if duty_key in fields:
        permille = _int_field(fields, duty_key)
        if not 0 <= permille <= 1000:
            raise AckTranslationError(f"DUTY_OUT_OF_RANGE: {duty_key}={permille}")
        action["duty"] = permille / 1000.0
    return action


def device_ack_to_backend(line: str) -> dict:
    """Render a device ``#CG CMDACK`` record as the CommandAck JSON envelope."""
    fields = parse_device_ack_fields(line)
    status = fields["status"]
    if status not in ACK_STATUS_VOCABULARY:
        raise AckTranslationError(f"UNKNOWN_STATUS: {status!r}")
    if _int_field(fields, "schema") != 1:
        raise AckTranslationError("UNSUPPORTED_SCHEMA: device ACK schema must be 1")

    envelope: dict = {
        "schema_version": 1,
        "command_id": fields["command_id"],
        "device_id": fields["device_id"],
        "boot_id": fields["boot_id"],
        "status": status,
        "reason_code": fields["reason"],
        "uptime_ms": _int_field(fields, "uptime_ms"),
    }

    canonical = fields.get("canonical_status")
    if status == "DUPLICATE_CANONICAL":
        if canonical is None or canonical not in ACK_STATUS_VOCABULARY:
            raise AckTranslationError(
                "DUPLICATE_MISSING_CANONICAL: DUPLICATE_CANONICAL requires the "
                "original verdict in canonical_status"
            )
    if canonical is not None:
        if canonical not in ACK_STATUS_VOCABULARY:
            raise AckTranslationError(f"UNKNOWN_CANONICAL_STATUS: {canonical!r}")
        envelope["canonical_status"] = canonical

    if "ack_seq" in fields:
        envelope["ack_seq"] = _int_field(fields, "ack_seq")
    for name in ("reapplied", "expiry_evaluable"):
        value = _bool01(fields, name)
        if value is not None:
            envelope[name] = value
    if "time_sync_state" in fields:
        if fields["time_sync_state"] not in ("SYNCHRONIZED", "UNSYNCHRONIZED"):
            raise AckTranslationError(f"INVALID_TIME_SYNC: {fields['time_sync_state']!r}")
        envelope["time_sync_state"] = fields["time_sync_state"]
    if "output_stage" in fields:
        if fields["output_stage"] not in ("ENABLED", "DISABLED"):
            raise AckTranslationError(f"INVALID_OUTPUT_STAGE: {fields['output_stage']!r}")
        envelope["output_stage"] = fields["output_stage"]
    if "device_mode" in fields:
        envelope["device_mode"] = fields["device_mode"]
    if "fault_code" in fields:
        envelope["fault_code"] = fields["fault_code"]

    desired = _action(fields, "desired_cooling", "desired_duty_permille")
    if desired is not None:
        envelope["desired"] = desired
    applied = _action(fields, "applied_cooling", "applied_duty_permille")
    if applied is not None:
        envelope["applied"] = applied
    return envelope