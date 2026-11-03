"""ColdGuard W04 raw telemetry schema and parser (standard library only).

Schema 1 is the ``#CG TELEM`` line emitted once per second by
``firmware/main/cg_telemetry.c``. This module turns that line into typed
records for the acquisition and ML builders.

Evidence rules encoded here:

* The device has no wall clock. ``timestamp_utc`` is the literal token
  ``UNAVAILABLE``; it is never replaced with the host clock during
  extraction, because a host timestamp on a device line would be an
  invented measurement time. A line that carries any other timestamp or
  provenance token is rejected, not repaired. Derived files keep it as
  ``None`` plus ``timestamp_utc_status=UNAVAILABLE``.
* ``nan`` means missing: it becomes ``None``, never 0.0. A numeric value
  is only usable when its companion ``*_status`` token is ``OK``; the
  builder masks contradictions instead of trusting the number.
* ``raw`` keeps the exact device line, so the immutable capture remains
  traceable after extraction.
* Unknown ``key=value`` tokens are retained (forward compatibility) but
  required schema-1 fields must all be present; a truncated or
  incompatible line is rejected, not repaired.
"""

from __future__ import annotations

import dataclasses
import math
import re

SCHEMA_VERSION = 1
PREFIX = "#CG TELEM"
MISSING_TOKEN = "nan"
UTC_UNAVAILABLE = "UNAVAILABLE"
UTC_SOURCE_NO_WALL_CLOCK = "DEVICE_HAS_NO_WALL_CLOCK"

# Exactly the fields the A-W04 data contract asks a capture to carry.
REQUIRED_FIELDS = (
    "timestamp_utc",
    "elapsed_ms",
    "run_id",
    "boot_id",
    "firmware_version",
    "hardware_config_id",
    "test_phase",
    "t_inside_c",
    "t_cold_side_c",
    "t_hot_side_c",
    "t_ambient_c",
    "relative_humidity_pct",
    "door_open",
    "voltage_v",
    "current_a",
    "power_w",
    "pwm_duty",
    "fan_command",
    "sensor_validity",
    "fault_code",
)

# The status/provenance companion of every value field is required too: a
# value without a status cannot be interpreted.
REQUIRED_STATUS_FIELDS = (
    "t_inside_status",
    "t_cold_side_status",
    "t_hot_side_status",
    "t_ambient_status",
    "relative_humidity_status",
    "voltage_status",
    "current_status",
    "power_status",
    "door_status",
    "fault_reason",
    "t_inside_src",
    "timestamp_utc_source",
    "output_stage",
    "tec_state",
    "fan_status",
    "power_validity",
)

FLOAT_FIELDS = {
    "t_inside_c",
    "t_cold_side_c",
    "t_hot_side_c",
    "t_ambient_c",
    "relative_humidity_pct",
    "voltage_v",
    "current_a",
    "power_w",
}

INTEGER_FIELDS = {
    "schema",
    "uptime_ms",
    "elapsed_ms",
    "run_elapsed_ms",
    "boot_count",
    "pwm_duty",
    "door_raw",
}

# Fields whose numeric value is only trustworthy when their status is OK.
VALUE_STATUS_PAIRS = {
    "t_inside_c": "t_inside_status",
    "t_cold_side_c": "t_cold_side_status",
    "t_hot_side_c": "t_hot_side_status",
    "t_ambient_c": "t_ambient_status",
    "relative_humidity_pct": "relative_humidity_status",
    "voltage_v": "voltage_status",
    "current_a": "current_status",
    "power_w": "power_status",
    "door_open": "door_status",
}

HEX_RE = re.compile(r"^0[xX][0-9A-Fa-f]{1,8}$")
FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
INT_RE = re.compile(r"^[+-]?\d+$")


class TelemetryError(ValueError):
    """Raised for a line that is not a well-formed schema-1 telemetry line."""


@dataclasses.dataclass(frozen=True)
class TelemetryRecord:
    """One parsed ``#CG TELEM`` line.

    ``raw_fields`` holds every token exactly as sent; ``fields`` holds the
    typed view used by the builders. ``line_index`` is the 1-based line
    number in the capture, so a rejected neighbour can be located.
    """

    line_index: int
    raw: str
    raw_fields: dict[str, str]
    fields: dict[str, object]

    def value(self, name: str) -> object:
        return self.fields.get(name)

    def status(self, name: str) -> str | None:
        status_name = VALUE_STATUS_PAIRS.get(name)
        if status_name is None:
            return None
        status = self.fields.get(status_name)
        return status if isinstance(status, str) else None

    def usable(self, name: str) -> bool:
        """True only when the value is a number and its status is OK."""
        return self.value(name) is not None and self.status(name) == "OK"


def _coerce(name: str, token: str) -> object:
    if name in FLOAT_FIELDS:
        if token == MISSING_TOKEN:
            return None
        if not FLOAT_RE.match(token):
            raise TelemetryError(f"field {name!r} is not a number or {MISSING_TOKEN}: {token!r}")
        value = float(token)
        if not math.isfinite(value):
            raise TelemetryError(f"field {name!r} is not a finite number: {token!r}")
        return value
    if name in INTEGER_FIELDS:
        if not INT_RE.match(token):
            raise TelemetryError(f"field {name!r} is not an integer: {token!r}")
        return int(token)
    if name == "door_open":
        if token == MISSING_TOKEN:
            return None
        if token in ("0", "1"):
            return int(token)
        raise TelemetryError(f"door_open is neither 0, 1 nor {MISSING_TOKEN}: {token!r}")
    if name == "fault_code":
        if not HEX_RE.match(token):
            raise TelemetryError(f"fault_code is not hexadecimal: {token!r}")
        return int(token, 16)
    return token


def parse_line(line: str, line_index: int = 0) -> TelemetryRecord:
    """Parse one telemetry line; raise TelemetryError if it is not schema 1."""
    text = line.rstrip("\r\n")
    tokens = text.split(" ")
    if len(tokens) < 3 or tokens[0] != "#CG" or tokens[1] != "TELEM":
        raise TelemetryError("not a '#CG TELEM' line")

    raw_fields: dict[str, str] = {}
    for token in tokens[2:]:
        if token == "":
            raise TelemetryError("empty token (truncated line?)")
        if "=" not in token:
            raise TelemetryError(f"token without '=': {token!r} (truncated line?)")
        key, value = token.split("=", 1)
        if not key or value == "":
            raise TelemetryError(f"empty key or value in {token!r}")
        if key in raw_fields:
            raise TelemetryError(f"duplicate field {key!r}")
        raw_fields[key] = value

    schema = raw_fields.get("schema")
    if schema is None:
        raise TelemetryError("missing schema field")
    if schema != str(SCHEMA_VERSION):
        raise TelemetryError(f"schema {schema!r} is not supported (expected {SCHEMA_VERSION})")

    missing = [name for name in REQUIRED_FIELDS + REQUIRED_STATUS_FIELDS if name not in raw_fields]
    if missing:
        raise TelemetryError("missing required fields: " + ", ".join(missing))

    # The device has no wall clock. A schema-1 line that carries a timestamp
    # (or a different provenance token) did not come from this firmware, and
    # accepting it would let an invented measurement time into the dataset.
    if raw_fields["timestamp_utc"] != UTC_UNAVAILABLE:
        raise TelemetryError(
            f"timestamp_utc must be {UTC_UNAVAILABLE!r}, got {raw_fields['timestamp_utc']!r}"
        )
    if raw_fields["timestamp_utc_source"] != UTC_SOURCE_NO_WALL_CLOCK:
        raise TelemetryError(
            "timestamp_utc_source must be "
            f"{UTC_SOURCE_NO_WALL_CLOCK!r}, got {raw_fields['timestamp_utc_source']!r}"
        )

    fields: dict[str, object] = {}
    for key, value in raw_fields.items():
        fields[key] = _coerce(key, value)

    return TelemetryRecord(line_index=line_index, raw=text, raw_fields=raw_fields, fields=fields)


def read_capture(path_or_lines) -> tuple[list[TelemetryRecord], dict]:
    """Parse every telemetry line from a capture, keeping rejection reasons.

    Accepts a path or an iterable of lines. Non-telemetry lines (boot
    noise, operator notes, other ``#CG`` kinds) are counted as ignored;
    telemetry-looking lines that fail validation are counted as rejected
    with their reason. Nothing is dropped silently.
    """
    if isinstance(path_or_lines, (str, bytes)) or hasattr(path_or_lines, "read_text"):
        import pathlib

        text = pathlib.Path(path_or_lines).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
    else:
        lines = list(path_or_lines)

    records: list[TelemetryRecord] = []
    rejected: list[dict[str, object]] = []
    ignored = 0

    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped.startswith(PREFIX):
            ignored += 1
            continue
        try:
            records.append(parse_line(line, line_index=number))
        except TelemetryError as exc:
            rejected.append({"line_index": number, "reason": str(exc), "raw": line.rstrip("\r\n")})

    report = {
        "lines_total": len(lines),
        "records": len(records),
        "ignored": ignored,
        "rejected": rejected,
    }
    return records, report
