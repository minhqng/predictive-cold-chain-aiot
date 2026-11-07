"""Strict runtime telemetry validation and topic/device identity (C-W03-01/02).

W01 :mod:`coldguard_backend.contracts` validates wire *shape* with
Pydantic's default (lax) coercion. That is insufficient for W03
authority: lax coercion would silently transform a semantically invalid
wire value into a valid identity or measurement (e.g. ``seq="42"`` →
``42``, ``t1="7.1"`` → ``7.1``, ``seq=true`` → ``1``). This module is
the strict gate in front of those contracts:

* exact-type pre-checks reject string/bool/float values where the
  canonical wire model requires a string, an exact integer, or a JSON
  number — before Pydantic ever sees them;
* ``schema_version`` must be a supported value (currently ``1``); an
  unsupported schema is rejected, never parsed as if compatible;
* ``captured_at`` must carry timezone information (canonical event-time
  interpretation; a naive timestamp is ambiguous and therefore
  rejected);
* the measurement/quality contract from Doc 01/02 is enforced by the
  underlying contracts (``VALID`` quality requires complete values;
  ``None`` under ``VALID`` fails; ``DEGRADED`` may still carry usable
  readings; missing/invalid/degraded/zero are never equated and no
  value is fabricated);
* topic/device agreement (C-W03-02): for telemetry topics the MQTT
  topic device segment must equal ``payload.device_id``. A mismatch —
  or a malformed telemetry namespace — never yields a normalized
  sample. Raw diagnostic evidence is preserved by the caller.

Trust boundary (Doc 02 §12): the broker authenticates the MQTT
principal and scopes topics via ACL; the backend receives only
topic/payload through its subscribed connection. There is no
authenticated publisher username inside an ordinary PUBLISH packet, so
this module proves *topic/payload agreement only* — never broker
authentication. No fake publisher-identity field is introduced and no
self-declared payload claim is trusted as authentication proof.
"""

from __future__ import annotations

import math
import re
from typing import Any

from pydantic import ValidationError

from coldguard_backend.contracts import Telemetry

SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})

# Canonical telemetry namespace: coldguard/{device_id}/telemetry.
# The device segment is one non-empty path element; MQTT wildcards and
# empty segments are never valid device identities on the wire.
_TELEMETRY_TOPIC_RE = re.compile(r"^coldguard/([^/+#]+)/telemetry$")
_TELEMETRY_SUFFIX = "/telemetry"

# Wire fields that must be JSON numbers (int or float, never bool/str)
# when present. None marks a missing channel (quality-gated downstream).
_NUMERIC_PATHS = (
    ("thermal", "t1"),
    ("thermal", "t2"),
    ("thermal", "t3"),
    ("environment", "t_air"),
    ("environment", "rh"),
    ("electrical", "voltage_v"),
    ("electrical", "current_a"),
    ("electrical", "power_w"),
    ("electrical", "energy_wh"),
    ("actuation", "duty"),
)

# Wire fields that must be strings when present.
_STRING_PATHS = (
    ("device_id",),
    ("boot_id",),
    ("captured_at",),
    ("hardware_config_id",),
    ("firmware_version",),
    ("run_id",),
    ("calibration_id",),
    ("door", "state"),
    ("actuation", "cooling"),
    ("quality", "thermal"),
    ("quality", "environment"),
    ("quality", "electrical"),
    ("quality", "overall"),
    ("quality", "device_mode"),
    ("serial_source", "clock_quality"),
    ("serial_source", "gateway_received_at"),
    ("serial_source", "frame"),
)

# Wire fields that must be exact integers (type(x) is int: bool, str and
# float are rejected even when Pydantic would coerce them).
_EXACT_INT_PATHS = (
    ("schema_version",),
    ("seq",),
    ("uptime_ms",),
    ("serial_source", "schema_version"),
)


def _get_path(payload: Any, path: tuple[str, ...]) -> tuple[bool, Any]:
    """Return (present, value) for a nested dict path."""
    node = payload
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return False, None
        node = node[key]
    return True, node


def topic_device_id(topic: str) -> str | None:
    """Device segment of a canonical telemetry topic, else None.

    Returns None for non-telemetry topics *and* for malformed telemetry
    namespaces (wrong prefix, empty/wildcard segment, extra elements).
    Use :func:`looks_like_telemetry_topic` to distinguish the two.
    """
    match = _TELEMETRY_TOPIC_RE.match(topic)
    if not match:
        return None
    segment = match.group(1)
    if not segment.strip():
        return None
    return segment


def looks_like_telemetry_topic(topic: str) -> bool:
    """True when the topic claims the telemetry family (valid or not)."""
    return topic.endswith(_TELEMETRY_SUFFIX)


def strict_type_errors(parsed: Any) -> list[dict[str, Any]]:
    """Exact-type violations that lax Pydantic coercion would hide."""
    errors: list[dict[str, Any]] = []
    if not isinstance(parsed, dict):
        return errors
    for path in _EXACT_INT_PATHS:
        present, value = _get_path(parsed, path)
        if present and type(value) is not int:
            errors.append(
                {
                    "code": "WRONG_TYPE",
                    "loc": ".".join(path),
                    "message": f"{'.'.join(path)} must be an integer identity/counter, "
                    f"got {type(value).__name__}",
                }
            )
    for path in _STRING_PATHS:
        present, value = _get_path(parsed, path)
        if present and value is not None and type(value) is not str:
            errors.append(
                {
                    "code": "WRONG_TYPE",
                    "loc": ".".join(path),
                    "message": f"{'.'.join(path)} must be a string, "
                    f"got {type(value).__name__}",
                }
            )
    for path in _NUMERIC_PATHS:
        present, value = _get_path(parsed, path)
        if present and value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            errors.append(
                {
                    "code": "WRONG_TYPE",
                    "loc": ".".join(path),
                    "message": f"{'.'.join(path)} must be a JSON number or null, "
                    f"got {type(value).__name__}",
                }
            )
        elif (
            present
            and isinstance(value, float)
            and not math.isfinite(value)
        ):
            # Python's json parser accepts NaN/Infinity literals; they are
            # impossible physical readings (Doc 01 invalid measurement)
            # and NaN would additionally poison duplicate comparison
            # (NaN != NaN), so they are rejected, never stored.
            errors.append(
                {
                    "code": "NON_FINITE",
                    "loc": ".".join(path),
                    "message": f"{'.'.join(path)} must be a finite number",
                }
            )
    for section in ("thermal", "environment", "door", "electrical", "actuation", "quality"):
        if section in parsed and not isinstance(parsed[section], dict):
            errors.append(
                {
                    "code": "WRONG_TYPE",
                    "loc": section,
                    "message": f"{section} must be an object, "
                    f"got {type(parsed[section]).__name__}",
                }
            )
    return errors


def validate_telemetry_payload(parsed: Any) -> tuple[Telemetry | None, list[dict[str, Any]]]:
    """Strict-validate a parsed telemetry document.

    Returns (telemetry, []) on success; (None, errors) on any failure
    (wrong types, contract violation, unsupported schema, naive
    timestamp). An unsupported ``schema_version`` is always a failure:
    it is never parsed as if it were a compatible schema.
    """
    errors = strict_type_errors(parsed)
    if errors:
        return None, errors
    if isinstance(parsed, dict):
        version = parsed.get("schema_version")
        if type(version) is int and version not in SUPPORTED_SCHEMA_VERSIONS:
            return None, [
                {
                    "code": "UNSUPPORTED_SCHEMA",
                    "loc": "schema_version",
                    "message": f"unsupported schema_version {version!r}; "
                    f"supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}",
                }
            ]
    try:
        telemetry = Telemetry.model_validate(parsed)
    except ValidationError as exc:
        return None, [
            {
                "code": "SCHEMA_VIOLATION",
                "loc": ".".join(str(part) for part in err.get("loc", ())),
                "message": str(err.get("msg", ""))[:500],
            }
            for err in exc.errors()[:20]
        ]
    if telemetry.captured_at is not None and telemetry.captured_at.tzinfo is None:
        return None, [
            {
                "code": "NAIVE_TIMESTAMP",
                "loc": "captured_at",
                "message": "captured_at must carry timezone information "
                "(canonical UTC event time); naive timestamps are rejected",
            }
        ]
    return telemetry, []


def validate_topic_identity(topic: str, telemetry: Telemetry) -> list[dict[str, Any]]:
    """Check topic device segment against payload device_id.

    Returns [] on agreement; otherwise a TOPIC_MISMATCH or
    MALFORMED_TOPIC diagnostic. The backend proves agreement only —
    never broker authentication (see module trust-boundary note).
    """
    device_segment = topic_device_id(topic)
    if device_segment is None:
        return [
            {
                "code": "MALFORMED_TOPIC",
                "loc": "topic",
                "message": f"telemetry topic {topic!r} is not "
                "coldguard/{device_id}/telemetry with a valid device segment",
            }
        ]
    if device_segment != telemetry.device_id:
        return [
            {
                "code": "TOPIC_MISMATCH",
                "loc": "device_id",
                "message": f"topic device {device_segment!r} disagrees with "
                f"payload device_id {telemetry.device_id!r}; no normalized "
                "sample is created",
            }
        ]
    return []
