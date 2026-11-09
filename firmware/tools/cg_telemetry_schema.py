"""ColdGuard raw telemetry schema and parser (standard library only).

Schema 1 is the ``#CG TELEM`` line emitted by the W04 delivery. Schema 2 adds
the W05 telemetry foundation: device identity, per-field ages, the canonical
data-quality vocabulary, producer liveness, accumulated energy, and the applied
cooling state kept separate from the requested one. Schema 3 adds the W06
command layer: the desired cooling state and the last command ACK verdict, kept
apart from the applied state so "was asked" and "is doing" cannot be conflated
downstream.

All three parse. A capture taken before W05 - the committed W04 evidence in
``evidence/A/W04/`` - and the W05 fixture must stay readable, and the tests pin
that: raising the firmware's serial schema does not rewrite history.

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
  required fields for the line's own schema must all be present; a truncated
  or incompatible line is rejected, not repaired.
* A ``*_src`` token names a *slot*, and a slot says nothing by itself about
  whether its probe sits in chamber air or on the TEC hot side. ``source_rom``
  and ``source_position`` resolve it through the line's own ``t1_rom``..
  ``spare_rom`` fields to the frozen as-built position, so a consumer can prove
  which ROM produced a chamber value instead of assuming the field name was
  honest. Historical lines are never relabelled: the committed pre-W06 frames
  that say ``t_inside_src=T2`` still parse, and ``chamber_source_is_hot_side``
  is the read-only gate over them.
* Vocabulary fields are checked against their closed token sets. A quality
  name that is not one of ``VALID/DEGRADED/INVALID/UNKNOWN`` (docs/01 2263-2308)
  is a contract violation, so rejecting it is the only way to keep
  ``UNKNOWN`` from silently becoming something else downstream.
"""

from __future__ import annotations

import dataclasses
import math
import re

SCHEMA_VERSION = 3
SUPPORTED_SCHEMAS = (1, 2, 3)
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

# A-W05-02 / -04 / -05 and the applied-state split. These are mandatory on a
# schema-2 line: the point of W05 is that a frame states its own identity,
# freshness and quality instead of leaving the reader to assume them.
W05_REQUIRED_FIELDS = (
    "device_id",
    "seq",
    "calibration_id",
    "energy_wh",
    "energy_status",
    "thermal_age_ms",
    "power_age_ms",
    "door_age_ms",
    "thermal_seq",
    "power_seq",
    "door_transitions",
    "door_cycles",
    "probes_valid",
    "probes_expected",
    "thermal_quality",
    "environment_quality",
    "door_quality",
    "electrical_quality",
    "quality",
    "cooling_applied",
    "cooling_applied_source",
    "cooling_evidence",
    "health",
    "health_thermal",
    "health_bme",
    "health_door",
    "health_power",
    "health_telemetry",
    "health_control",
    "t1_rom",
    "t2_rom",
    "t3_rom",
    "spare_rom",
    "role_status",
    "rom_source",
)

# The line's age fields carry no separate status token: they *are* the status. A
# saturated value is therefore the sentinel the formatter writes when an
# observation is timestamped after the frame's own clock, which means the two
# clocks disagreed and no age can be trusted from that row.
AGE_SATURATION_SENTINEL = 18446744073709551615
AGE_FIELDS = ("thermal_age_ms", "power_age_ms", "door_age_ms")

# A-W06-04. Mandatory from schema 3: a frame that cannot say what it was asked to
# do cannot be used to audit a command lifecycle.
W06_REQUIRED_FIELDS = (
    "command_id",
    "desired_cooling",
    "desired_duty_permille",
    "last_ack_status",
    "last_ack_reason",
)

# Additive W06-era tokens: parsed, validated and retained, but deliberately not
# in any required set, so the committed schema-1 and schema-2 captures keep
# parsing. This is why the serial schema version stayed at 3 instead of a bump
# that would orphan the W04/W05 dossiers.
OPTIONAL_SOURCE_FIELDS = ("t_hot_side_src",)

# Fields that are integers when present and the literal `nan` when the device has
# no value to report. `desired_duty_permille=nan` next to `desired_cooling=NONE`
# is the honest "nothing was requested" state; coercing it to 0 would invent an
# explicit request to stay off.
NANABLE_INT_FIELDS = ("desired_duty_permille",)

FLOAT_FIELDS = {
    "raw_t1_c",
    "raw_t2_c",
    "raw_t3_c",
    "raw_spare_c",
    "t_inside_c",
    "t_cold_side_c",
    "t_hot_side_c",
    "t_ambient_c",
    "relative_humidity_pct",
    "voltage_v",
    "current_a",
    "power_w",
    "energy_wh",
}

INTEGER_FIELDS = {
    "schema",
    "uptime_ms",
    "elapsed_ms",
    "run_elapsed_ms",
    "boot_count",
    "pwm_duty",
    "door_raw",
    "seq",
    "thermal_age_ms",
    "power_age_ms",
    "door_age_ms",
    "thermal_seq",
    "power_seq",
    "door_transitions",
    "door_cycles",
    "probes_valid",
    "probes_expected",
    "thermal_beats",
    "power_beats",
    "door_beats",
    "control_beats",
    "telemetry_beats",
    "thermal_max_gap_ms",
    "power_max_gap_ms",
    "door_max_gap_ms",
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
    "energy_wh": "energy_status",
    "door_open": "door_status",
}

# Closed vocabularies. docs/01 2263-2308 freezes the four quality states; the
# producer-health names are the firmware's cg_health_state_t plus the explicit
# "not evaluated" value the formatter emits when no report was supplied.
QUALITY_VOCABULARY = ("VALID", "DEGRADED", "INVALID", "UNKNOWN")
QUALITY_FIELDS = (
    "thermal_quality",
    "environment_quality",
    "door_quality",
    "electrical_quality",
    "quality",
)
# `sensor_validity` is the W04 legacy field. On a schema-1 line it carried the
# thermal quality name, and it also carried NO_DATA before the first sample -
# which is still true in schema 2 - so its accepted set is the quality vocabulary
# plus that token. The five W05 names above are checked strictly.
LEGACY_VOCABULARY = ("sensor_validity",)
LEGACY_EXTRA_TOKENS = ("NO_DATA",)
HEALTH_VOCABULARY = ("OK", "LATE", "MISSED", "NEVER", "UNKNOWN")
HEALTH_FIELDS = (
    "health",
    "health_thermal",
    "health_bme",
    "health_door",
    "health_power",
    "health_telemetry",
    "health_control",
)
COOLING_APPLIED_VOCABULARY = ("ON", "OFF")
COOLING_EVIDENCE_VOCABULARY = (
    "MEASURED_APPLIED_AND_DRAWING",
    "MEASURED_IDLE_AND_ZERO",
    "MEASURED_CONTRADICTS_APPLIED",
    "UNOBSERVED_STALE",
    "UNOBSERVED_NO_DATA",
)
OUTPUT_STAGE_VOCABULARY = ("ENABLED", "DISABLED")
# docs/02 §32.1 (lines 2172-2186) closes the ACK status set. The command layer may not
# invent a
# verdict, and neither may the parser quietly accept one.
ACK_STATUS_VOCABULARY = (
    "ACCEPTED",
    "REJECTED",
    "DUPLICATE_CANONICAL",
    "EXPIRED",
    "SAFETY_BLOCKED",
    "INVALID_STATE",
    "OUT_OF_RANGE",
)
# `NONE` in the telemetry line means no command has been received in this boot.
# That is not an ACK status and must not be coerced into one.
TELEM_ACK_STATUS_VOCABULARY = ("NONE",) + ACK_STATUS_VOCABULARY
# docs/01 2174-2189 fixes the cooling vocabulary at ON/OFF; NONE is the
# no-command-received case.
DESIRED_COOLING_VOCABULARY = ("NONE", "ON", "OFF")
ROM_TOKEN_LEN = 16
ROM_UNREAD = "UNREAD"

# --- Probe role authority ----------------------------------------------------
# ROM -> physical position, keyed on the 8 ROM bytes rather than on a slot
# literal. The strings are deliberately identical to the host role authority in
# ``firmware/tools/cg_probe_roles.py`` (A-W07-plant-repeatability worktree): if
# the two layers named the same probe differently, a chamber-air aggregate could
# silently re-admit the hot side again.
#
# This is the operator-frozen as-built record, not a remeasurement - independent
# proof of no movement after the freeze is NOT_AVAILABLE (IHA-01 level 4) - and
# it never relabels a historical capture. It resolves the *present* line only.
HOT_SIDE_ROM = "28AEBF2200000006"
ROM_POSITION_BY_ROM = {
    "287088CA00000051": "CHAMBER_CENTER",
    "28AEBF2200000006": "TEC_HOT_SIDE",
    "28CBE9CA00000072": "CHAMBER_BOTTOM",
    "283BE5C9000000A9": "CHAMBER_NEAR_DOOR",
}
CHAMBER_AIR_ROMS = frozenset(
    rom for rom, position in ROM_POSITION_BY_ROM.items() if position != "TEC_HOT_SIDE"
)
CHAMBER_AIR_POSITIONS = frozenset({"CHAMBER_CENTER", "CHAMBER_BOTTOM", "CHAMBER_NEAR_DOOR"})
NON_AIR_POSITIONS = frozenset({"TEC_HOT_SIDE"})

# Slot -> ROM, the same direction `cg_probe_roles.SLOT_TO_ROM` publishes. `T4`
# is the spare slot's slot name; the line spells its ROM field `spare_rom`.
SLOT_TO_ROM = {
    "T1": "287088CA00000051",
    "T2": "28AEBF2200000006",
    "T3": "28CBE9CA00000072",
    "T4": "283BE5C9000000A9",
}

# The ``*_src`` token a line emits -> the field carrying that slot's ROM.
SRC_TOKEN_TO_ROM_FIELD = {
    "T1": "t1_rom",
    "T2": "t2_rom",
    "T3": "t3_rom",
    "T4": "spare_rom",
    "SPARE": "spare_rom",
}

# Slots the frozen map says are chamber air, in the uppercase slot vocabulary
# ``cg_serial.MEASUREMENT_ROLES`` uses. Callers that need an air-only spread pass
# these; the historical all-roles defaults are left alone so already published
# artifacts keep meaning what they meant.
CHAMBER_AIR_ROLE_NAMES = tuple(
    slot for slot, rom in SLOT_TO_ROM.items() if rom in CHAMBER_AIR_ROMS
)
HOT_SIDE_ROLE_NAME = "T2"


def position_of_rom(rom: str | None) -> str | None:
    """The frozen physical position of a ROM, or None when it is not in the map."""
    return ROM_POSITION_BY_ROM.get((rom or "").upper().strip())


def source_slot(record: TelemetryRecord, src_field: str) -> str | None:
    """The slot token a value field names as its source, normalised to the map."""
    token = record.fields.get(src_field)
    if not isinstance(token, str):
        return None
    key = token.upper()
    if key not in SRC_TOKEN_TO_ROM_FIELD:
        return None
    return "T4" if key == "SPARE" else key


def source_rom(record: TelemetryRecord, src_field: str) -> str | None:
    """The ROM a value field's ``*_src`` token names.

    Prefers the ROM the line itself carried (a per-frame cross-check of the
    frozen map against what the emitter put on the wire); falls back to the
    frozen slot table for the pre-W05 lines, which name a slot but carry no ROM
    field. Returns None only when the slot is unknown or reads ``UNREAD`` -
    absence of identity, which is not a claim of agreement.
    """
    slot = source_slot(record, src_field)
    if slot is None:
        return None
    rom = record.fields.get(SRC_TOKEN_TO_ROM_FIELD[slot])
    if isinstance(rom, str) and rom != ROM_UNREAD:
        return rom.upper()
    return SLOT_TO_ROM.get(slot)


def source_position(record: TelemetryRecord, src_field: str) -> str | None:
    """The frozen physical position behind a value field's ``*_src`` token."""
    return position_of_rom(source_rom(record, src_field))


def chamber_source_is_hot_side(record: TelemetryRecord) -> bool:
    """True when ``t_inside_c`` is reported as coming from the hot-side probe.

    Read-only: it names the defect instead of inventing a role, and it is what
    lets a consumer gate historical frames - every committed W04 line says
    ``t_inside_src=T2``, and the W04 cooling capture labels that slot
    ``t2_role=HOT_SIDE`` in all 957 rows - without the parser rewriting them.
    """
    return source_rom(record, "t_inside_src") == HOT_SIDE_ROM


def _check_source_tokens(fields: dict[str, object]) -> None:
    """A ``*_src`` token must name a slot, and a slot's ROM must be the frozen one.

    History is preserved on both counts: the closed set is the four known slots,
    so a pre-W05 ``t_inside_src=T2`` still parses, and lines that carry no ROM
    field are not asked for one. But a line that *does* put a ROM on the wire
    under a slot name is making an identity claim, and a claim that contradicts
    the frozen map means the probes moved - after which no chamber aggregate
    built from that capture means anything, so it is refused at the parser
    rather than passed through as provenance.
    """
    for name in ("t_inside_src", "t_hot_side_src"):
        token = fields.get(name)
        if isinstance(token, str) and token.upper() not in SRC_TOKEN_TO_ROM_FIELD:
            raise TelemetryError(
                f"{name}={token!r} names no slot in the frozen ROM map "
                f"({', '.join(sorted(SRC_TOKEN_TO_ROM_FIELD))})"
            )
    for slot, rom in SLOT_TO_ROM.items():
        carried = fields.get(SRC_TOKEN_TO_ROM_FIELD[slot])
        if isinstance(carried, str) and carried != ROM_UNREAD and carried != rom:
            raise TelemetryError(
                f"{SRC_TOKEN_TO_ROM_FIELD[slot]}={carried!r} is not the frozen ROM of "
                f"slot {slot} ({rom}); the as-built map and the device disagree"
            )

HEX_RE = re.compile(r"^0[xX][0-9A-Fa-f]{1,8}$")
FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
INT_RE = re.compile(r"^[+-]?\d+$")
ROM_RE = re.compile(r"^[0-9A-F]{16}$")


class TelemetryError(ValueError):
    """Raised for a line that is not a well-formed telemetry line."""


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
    if name in NANABLE_INT_FIELDS:
        if token == MISSING_TOKEN:
            return None
        if not INT_RE.match(token):
            raise TelemetryError(f"field {name!r} is not an integer or {MISSING_TOKEN}: {token!r}")
        value = int(token)
        if value < 0:
            raise TelemetryError(f"field {name!r} is negative: {token!r}")
        return value
    if name in INTEGER_FIELDS:
        if not INT_RE.match(token):
            raise TelemetryError(f"field {name!r} is not an integer: {token!r}")
        value = int(token)
        if value < 0:
            raise TelemetryError(f"field {name!r} is negative: {token!r}")
        return value
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


def _check_vocabulary(fields: dict[str, object]) -> None:
    for name in QUALITY_FIELDS:
        value = fields.get(name)
        if value is None:
            continue
        if value not in QUALITY_VOCABULARY:
            raise TelemetryError(
                f"{name}={value!r} is not one of {', '.join(QUALITY_VOCABULARY)}"
            )
    for name in LEGACY_VOCABULARY:
        value = fields.get(name)
        if value is None:
            continue
        allowed = QUALITY_VOCABULARY + LEGACY_EXTRA_TOKENS
        if value not in allowed:
            raise TelemetryError(f"{name}={value!r} is not one of {', '.join(allowed)}")
    for name in HEALTH_FIELDS:
        value = fields.get(name)
        if value is None:
            continue
        if value not in HEALTH_VOCABULARY:
            raise TelemetryError(
                f"{name}={value!r} is not one of {', '.join(HEALTH_VOCABULARY)}"
            )
    for name, allowed in (
        ("cooling_applied", COOLING_APPLIED_VOCABULARY),
        ("cooling_evidence", COOLING_EVIDENCE_VOCABULARY),
        ("output_stage", OUTPUT_STAGE_VOCABULARY),
    ):
        value = fields.get(name)
        if value is not None and value not in allowed:
            raise TelemetryError(f"{name}={value!r} is not one of {', '.join(allowed)}")


def _check_command_fields(fields: dict[str, object]) -> None:
    """A-W06-04 invariants a dataset must not be able to violate.

    A blocked or rejected request cannot become a desired state here, and a
    received command must name its id. That is what stops a downstream reader
    from treating a refused command as an applied one.
    """
    status = fields.get("last_ack_status")
    if isinstance(status, str) and status not in TELEM_ACK_STATUS_VOCABULARY:
        raise TelemetryError(
            f"last_ack_status={status!r} is not one of {', '.join(TELEM_ACK_STATUS_VOCABULARY)}"
        )
    desired = fields.get("desired_cooling")
    if isinstance(desired, str) and desired not in DESIRED_COOLING_VOCABULARY:
        raise TelemetryError(
            f"desired_cooling={desired!r} is not one of {', '.join(DESIRED_COOLING_VOCABULARY)}"
        )
    if desired in ("ON", "OFF") and status == "NONE":
        raise TelemetryError("desired_cooling set while no command was acknowledged")
    if desired == "NONE" and fields.get("command_id") != "NONE":
        raise TelemetryError("command_id present with desired_cooling=NONE")


def _check_identity(fields: dict[str, object]) -> None:
    """A-W05-02: identity must be self-consistent, not merely present."""
    if fields["device_id"] == "":
        raise TelemetryError("device_id is empty")
    if fields["seq"] < 1:
        raise TelemetryError(f"seq must start at 1 within a boot, got {fields['seq']}")
    for name in ("t1_rom", "t2_rom", "t3_rom", "spare_rom"):
        token = fields.get(name)
        if not isinstance(token, str):
            continue
        if token != ROM_UNREAD and not ROM_RE.match(token):
            raise TelemetryError(
                f"{name}={token!r} is not 16 uppercase hex bytes or {ROM_UNREAD}"
            )
    probes_valid = fields.get("probes_valid")
    probes_expected = fields.get("probes_expected")
    if isinstance(probes_valid, int) and isinstance(probes_expected, int):
        if probes_valid > probes_expected:
            raise TelemetryError(
                f"probes_valid={probes_valid} exceeds probes_expected={probes_expected}"
            )


def parse_line(line: str, line_index: int = 0) -> TelemetryRecord:
    """Parse one telemetry line; raise TelemetryError if it is malformed."""
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
    if schema not in {str(value) for value in SUPPORTED_SCHEMAS}:
        raise TelemetryError(
            f"schema {schema!r} is not supported (expected one of "
            f"{'/'.join(str(v) for v in SUPPORTED_SCHEMAS)})"
        )

    required = list(REQUIRED_FIELDS + REQUIRED_STATUS_FIELDS)
    if schema in ("2", "3"):
        required += list(W05_REQUIRED_FIELDS)
    if schema == "3":
        required += list(W06_REQUIRED_FIELDS)

    missing = [name for name in required if name not in raw_fields]
    if missing:
        raise TelemetryError("missing required fields: " + ", ".join(missing))

    # The device has no wall clock. A line that carries a timestamp (or a
    # different provenance token) did not come from this firmware, and
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

    _check_vocabulary(fields)
    _check_source_tokens(fields)
    if schema in ("2", "3"):
        _check_identity(fields)
    if schema == "3":
        _check_command_fields(fields)

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
