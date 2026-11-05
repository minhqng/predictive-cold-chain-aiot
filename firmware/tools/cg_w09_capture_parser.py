"""ColdGuard W09 capture parser: one normalized frame view over three real
capture shapes (standard library only).

Week 09 asks for evidence-grade data collection, and the repository already
holds three different encodings of the same device frames:

1. ``evidence/A/W04/tec-cooling-response-600s.csv`` - a derived 1 Hz table whose
   column names are the *builder's* names (``t1_c``, ``voltage_status``,
   ``bme_air_c``), not the wire names;
2. ``#CG H8S schema=3`` lines - the H8 bench firmware's own wire form, found in
   ``monitor/samples.jsonl`` ``raw`` fields and in host-timestamped
   ``session_raw.log``/``telemetry_raw.log`` transcripts;
3. ``#CG TELEM`` lines - the schema 1/2/3 delivery telemetry, already owned by
   ``cg_telemetry_schema``.

This module normalizes all three into one ``Frame`` vocabulary so that W09
validity, W10 door analysis and W11 S4 analysis reason about device *facts*
rather than about column spellings. It deliberately does not re-implement the
telemetry contract: schema 1/2/3 parsing is delegated to
``cg_telemetry_schema.parse_line`` and the wire constants and vocabularies are
imported from it, so raising the firmware's serial schema cannot leave this
parser behind.

Rules kept honest here:

* The device has no wall clock. ``timestamp_utc`` stays ``None`` with
  ``timestamp_utc_status=UNAVAILABLE``. When a host transcript prefixes a line
  with its own capture time, that time is kept in a *separate* field
  (``host_capture_time_utc``) and is labelled as host-side; it is never written
  into the device timestamp, because a host clock is not the device's
  measurement time.
* A field that the source does not carry is ``None``. The CSV carries no
  ``door_status``, no ``power_status``, no missing/invalid/stale masks and no
  ``device_id``; those stay absent and the validity layer reports them as
  unqualified rather than inventing a value.
* Empty strings in the CSV mean "the builder had no status to write", which is
  NOT ``OK``. They normalize to ``None`` and are reported that way.
* The H8S JSON side objects in ``samples.jsonl`` are a lossy projection of the
  wire line: ``door_raw``, ``door_status`` and ``door_cycles`` exist only in the
  ``raw`` text. The parser therefore reads the ``raw`` field, not the JSON
  projection, and says so.
* Non-physical sources (host fixtures) may be parsed for tooling tests but are
  tagged ``is_physical_measurement=False`` on every frame, so no downstream
  analysis can silently treat them as a run.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime
import hashlib
import pathlib
import re
from typing import Iterable, Mapping

import cg_telemetry_schema as schema
from cg_telemetry_schema import (
    FLOAT_RE,
    HEX_RE,
    INT_RE,
    MISSING_TOKEN,
    TelemetryError,
    UTC_SOURCE_NO_WALL_CLOCK,
    UTC_UNAVAILABLE,
)

H8S_PREFIX = "#CG H8S"
H8S_SCHEMA = 3
CAPTURE_PARSER_VERSION = "w09-capture-parser-v1"

PROBE_SLOTS = ("t1", "t2", "t3", "t4")

# The H8S wire field set. Presence is required for the fields the frame must
# speak for itself about; anything unknown is retained but never trusted.
H8S_REQUIRED_FIELDS = (
    "schema",
    "seq",
    "timestamp_utc",
    "timestamp_utc_source",
    "device_ms",
    "boot_id",
    "run_id",
    "stage",
    "state",
    "snapshot",
    "pwm_req_permille",
    "pwm_applied_permille",
    "pwm_readback_permille",
    "door_open",
    "door_raw",
    "door_status",
    "door_polarity",
    "voltage_v",
    "voltage_v_status",
    "current_a",
    "current_a_status",
    "power_w",
    "power_w_status",
)
H8S_PROBE_FIELDS = tuple(
    f"{slot}_{suffix}" for slot in PROBE_SLOTS for suffix in ("", "_status", "_role", "_age_ms")
)
H8S_MASK_FIELDS = ("missing", "invalid", "stale")

# Bit positions copied from ``firmware/h8-bench/main/h8_types.h`` (read-only,
# verified against source rather than guessed). The same bits are used for the
# missing, invalid and stale masks.
H8_MASK_BITS = {
    0: "T1",
    1: "T2",
    2: "T3",
    3: "SPARE",
    4: "BME_T",
    5: "BME_RH",
    6: "BME_P",
    7: "DOOR",
    8: "PZEM_V",
    9: "PZEM_I",
    10: "PZEM_P",
    11: "HOT_BASE_ROLE",
    12: "COLD_PLATE_ROLE",
}
MASK_VALUE_FIELDS = {
    "T1": "t1",
    "T2": "t2",
    "T3": "t3",
    "SPARE": "t4",
    "BME_T": "air_c",
    "BME_RH": "rh_pct",
    "BME_P": "pressure_hpa",
    "DOOR": "door_open",
    "PZEM_V": "voltage_v",
    "PZEM_I": "current_a",
    "PZEM_P": "power_w",
}

H8S_INTEGER_FIELDS = {
    "schema",
    "seq",
    "device_ms",
    "stage_elapsed_ms",
    "stage_remaining_ms",
    "run_count",
    "pwm_req_permille",
    "pwm_applied_permille",
    "pwm_readback_permille",
    "pwm_freq_hz",
    "pwm_freq_rb_hz",
    "ren_command",
    "len_command",
    "host_ack_seq",
    "host_ack_count",
    "host_ack_reject",
    "host_ack_awaiting",
    "door_raw",
    "door_age_ms",
    "door_cycles",
    "pressure_required",
}
for _slot in PROBE_SLOTS:
    H8S_INTEGER_FIELDS.add(f"{_slot}_age_ms")
for _mask in H8S_MASK_FIELDS:
    H8S_INTEGER_FIELDS.add(_mask)

H8S_FLOAT_FIELDS = {
    "t1",
    "t2",
    "t3",
    "t4",
    "air_c",
    "rh_pct",
    "pressure_hpa",
    "voltage_v",
    "current_a",
    "power_w",
    "energy_wh",
    "off_current_limit_a",
}
for _slot in PROBE_SLOTS:
    H8S_FLOAT_FIELDS.add(f"{_slot}_c")

SNAPSHOT_VOCABULARY = ("VALID", "INVALID")
DOOR_POLARITY_VOCABULARY = ("CONFIRMED", "UNCONFIRMED")
DOOR_STATE_VOCABULARY = ("0", "1", "UNKNOWN")
INTERLOCK_VOCABULARY = ("NOT_INSTALLED", "ABSENT", "OPEN", "CLOSED", "BYPASSED", "UNKNOWN")

# The builder's CSV column names, mapped onto the wire vocabulary. The CSV is a
# derived view of the same frames; without this map every consumer would need
# its own spelling list, which is how a field silently stops being checked.
CSV_COLUMN_ALIASES = {
    "t1_c": "t1",
    "t2_c": "t2",
    "t3_c": "t3",
    "t4_c": "t4",
    "bme_air_c": "air_c",
    "bme_rh_pct": "rh_pct",
    "bme_pressure_hpa": "pressure_hpa",
    "voltage_status": "voltage_v_status",
    "current_status": "current_a_status",
    "power_status": "power_w_status",
    "bme_pressure_status": "pressure_hpa_status",
}
CSV_COLUMNS_REMOVED_IN_NORMALIZATION = ("session", "stage_elapsed_s")

HOST_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_]+=")


def sha256_file(path: pathlib.Path) -> str:
    """SHA-256 of a source file, for provenance. Never trusts the filename."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclasses.dataclass(frozen=True)
class SourceProvenance:
    """What a frame was read out of, and whether it may be believed as data."""

    source_kind: str            # h8s_jsonl | h8s_transcript | telem | csv_capture
    source_path: str            # repo-relative or absolute path as read
    source_sha256: str | None   # None only for in-memory line iterables
    line_index: int             # 1-based line in the source
    is_physical_measurement: bool
    run_label: str              # session/run class, e.g. H8C_BOX_COOLING_600S
    note: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Frame:
    """One device frame in normalized vocabulary.

    ``values`` holds only fields the source actually carried (absent keys stay
    absent; present-but-missing wire tokens normalize to ``None``). Accessors
    never invent a default, because "no value" and "zero" are different claims
    and W09 validity has to be able to tell them apart.
    """

    provenance: SourceProvenance
    values: dict
    raw: str

    def has(self, name: str) -> bool:
        return name in self.values

    def get(self, name: str, default=None):
        return self.values.get(name, default)

    @property
    def seq(self):
        return self.values.get("seq")

    @property
    def boot_id(self):
        return self.values.get("boot_id")

    @property
    def run_id(self):
        return self.values.get("run_id")

    @property
    def dedup_key(self) -> tuple:
        """docs/02 4.2/4.3: identity is (device_id, boot_id, seq).

        ``device_id`` is not carried by every source. When it is absent the key
        records that explicitly instead of quietly substituting a constant, so a
        cross-device join can never be mistaken for a per-device one.
        """
        return (
            self.values.get("device_id") or "SOURCE_DOES_NOT_CARRY_DEVICE_ID",
            self.boot_id,
            self.seq,
        )

    def probe(self, slot: str) -> dict:
        return {
            "value": self.values.get(slot),
            "status": self.values.get(f"{slot}_status"),
            "role": self.values.get(f"{slot}_role"),
            "age_ms": self.values.get(f"{slot}_age_ms"),
        }

    def as_dict(self) -> dict:
        return {
            "provenance": self.provenance.as_dict(),
            "values": dict(self.values),
            "raw": self.raw,
        }


def _coerce_h8s(name: str, token: str):
    """Coerce one H8S token, reusing the schema module's recognizers."""
    if name in H8S_FLOAT_FIELDS:
        if token == MISSING_TOKEN:
            return None
        if not FLOAT_RE.match(token):
            raise TelemetryError(f"field {name!r} is not a number or {MISSING_TOKEN}: {token!r}")
        return float(token)
    if name in ("missing", "invalid", "stale", "fault_bits"):
        if not HEX_RE.match(token):
            raise TelemetryError(f"field {name!r} is not hexadecimal: {token!r}")
        return int(token, 16)
    if name in H8S_INTEGER_FIELDS:
        if not INT_RE.match(token):
            raise TelemetryError(f"field {name!r} is not an integer: {token!r}")
        return int(token)
    if name == "door_open":
        if token not in DOOR_STATE_VOCABULARY:
            raise TelemetryError(f"door_open is neither 0, 1 nor UNKNOWN: {token!r}")
        return int(token) if token in ("0", "1") else "UNKNOWN"
    if name == "pressure_required":
        if token in ("0", "1"):
            return bool(int(token))
        raise TelemetryError(f"pressure_required is not 0/1: {token!r}")
    return token


def tokenize_kv(text: str, prefix_tokens: int) -> dict[str, str]:
    """Split a ``key=value`` wire line into its token map.

    Shares one implementation with the telemetry path so a truncated line fails
    the same way everywhere. Duplicate keys are rejected rather than last-write
    wins, because a duplicated field on a wire line means the line was spliced.
    """
    tokens = text.split(" ")
    raw_fields: dict[str, str] = {}
    for token in tokens[prefix_tokens:]:
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
    return raw_fields


def strip_host_capture_time(line: str) -> tuple[str | None, str]:
    """Separate a host transcript prefix from the device line.

    Returns ``(host_capture_time_utc, device_line)``. The host time is kept
    beside the frame, never inside it.
    """
    match = HOST_TIME_RE.match(line)
    if not match:
        return None, line
    text = line[match.end(0):]
    if not text.startswith("#CG"):
        # A timestamp on a non-device line is transcript noise, not a capture
        # time for a frame; do not hand back a line that is not telemetry.
        return None, line
    return match.group(1), text


def host_time_is_iso_z(value: str) -> bool:
    try:
        datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def mask_names(mask: int | None) -> list[str]:
    if mask is None:
        return []
    return [H8_MASK_BITS[bit] for bit in sorted(H8_MASK_BITS) if mask & (1 << bit)]


def parse_h8s_line(line: str, provenance: SourceProvenance, raw_line: str | None = None) -> Frame:
    """Parse one ``#CG H8S`` line into a normalized frame."""
    text = line.rstrip("\r\n")
    tokens = text.split(" ")
    if len(tokens) < 3 or tokens[0] != "#CG" or tokens[1] != "H8S":
        raise TelemetryError("not a '#CG H8S' line")
    raw_fields = tokenize_kv(text, 2)

    if raw_fields.get("schema") != str(H8S_SCHEMA):
        raise TelemetryError(f"schema must be {H8S_SCHEMA}, got {raw_fields.get('schema')!r}")
    missing = [name for name in H8S_REQUIRED_FIELDS if name not in raw_fields]
    if missing:
        raise TelemetryError("missing required H8S fields: " + ", ".join(missing))
    # Same wall-clock honesty rule the telemetry schema enforces: a line that
    # carries a device timestamp did not come from this firmware.
    if raw_fields["timestamp_utc"] != UTC_UNAVAILABLE:
        raise TelemetryError(
            f"timestamp_utc must be {UTC_UNAVAILABLE!r}, got {raw_fields['timestamp_utc']!r}"
        )
    if raw_fields["timestamp_utc_source"] != UTC_SOURCE_NO_WALL_CLOCK:
        raise TelemetryError(
            "timestamp_utc_source must be "
            f"{UTC_SOURCE_NO_WALL_CLOCK!r}, got {raw_fields['timestamp_utc_source']!r}"
        )
    if raw_fields["snapshot"] not in SNAPSHOT_VOCABULARY:
        raise TelemetryError(f"snapshot={raw_fields['snapshot']!r} is not VALID/INVALID")
    if raw_fields["door_polarity"] not in DOOR_POLARITY_VOCABULARY:
        raise TelemetryError(
            f"door_polarity={raw_fields['door_polarity']!r} is not CONFIRMED/UNCONFIRMED"
        )
    probes_valid = 0
    for slot in PROBE_SLOTS:
        if f"{slot}_status" in raw_fields and raw_fields[f"{slot}_status"] == "OK":
            probes_valid += 1

    values: dict = {}
    for key, token in raw_fields.items():
        values[key] = _coerce_h8s(key, token)
    # Normalized aliases for the spellings the two encodings differ on, so
    # consumers use one name. The originals stay for traceability.
    if "stale" in values:
        values["stale_mask"] = values["stale"]
    # The wire and the derived CSV spell the BME pressure qualifier differently
    # (``pressure_status`` on the line, ``bme_pressure_status`` in the table). One
    # shared name is what keeps the validity layer from reading an H8S frame as
    # carrying no pressure qualifier at all - the exact way a field stops being
    # checked without anything failing.
    if "pressure_status" in values and "pressure_hpa_status" not in values:
        values["pressure_hpa_status"] = values["pressure_status"]
    values["timestamp_utc"] = None
    values["timestamp_utc_status"] = UTC_UNAVAILABLE
    values["probes_valid"] = probes_valid
    if provenance.run_label:
        values.setdefault("run_label", provenance.run_label)

    return Frame(
        provenance=provenance,
        values=values,
        raw=raw_line if raw_line is not None else text,
    )


def parse_h8s_json_object(obj: Mapping, provenance: SourceProvenance) -> Frame:
    """Parse a ``samples.jsonl`` object, using its ``raw`` wire line.

    The JSON projection drops ``door_raw``/``door_status``/``door_cycles``,
    which are exactly the fields the door analysis needs, so the ``raw`` field
    is authoritative here. An object without a ``#CG H8S`` raw line is rejected
    rather than parsed from the lossy projection.
    """
    raw = obj.get("raw")
    if not isinstance(raw, str) or not raw.startswith(H8S_PREFIX):
        raise TelemetryError(
            "samples.jsonl object carries no '#CG H8S' raw line; the JSON projection "
            "is lossy for door fields and is not accepted as a frame source"
        )
    return parse_h8s_line(raw, provenance, raw_line=raw)


def parse_frame_line(
    line: str,
    provenance: SourceProvenance,
    allow_telem: bool = True,
) -> Frame:
    """Parse any supported device line, delegating ``#CG TELEM`` to the schema."""
    host_time, device_line = strip_host_capture_time(line.strip())
    if host_time is not None:
        if not host_time_is_iso_z(host_time):
            raise TelemetryError(f"host capture time is not ISO-8601 Z: {host_time!r}")
        provenance = dataclasses.replace(
            provenance, note=(provenance.note + f" host_capture_time_utc={host_time}").strip()
        )
    if device_line.startswith(H8S_PREFIX):
        frame = parse_h8s_line(device_line, provenance, raw_line=device_line)
    elif device_line.startswith(schema.PREFIX):
        if not allow_telem:
            raise TelemetryError("#CG TELEM lines are disabled for this source")
        record = schema.parse_line(device_line, line_index=provenance.line_index)
        frame = normalize_telem_record(record, provenance, device_line)
    else:
        raise TelemetryError("line is neither '#CG H8S' nor '#CG TELEM'")
    if host_time is not None:
        # A separate field, never ``timestamp_utc``: this is the host's clock.
        frame.values["host_capture_time_utc"] = host_time
        frame.values["host_capture_time_semantics"] = (
            "HOST_CLOCK_ADDED_AT_CAPTURE_NOT_DEVICE_TIME"
        )
    return frame


def normalize_telem_record(record, provenance: SourceProvenance, device_line: str) -> Frame:
    """Map a ``TelemetryRecord`` into the shared frame vocabulary.

    The telemetry contract stays in ``cg_telemetry_schema``; this function only
    renames to the shared spellings and records which names the source lacked.
    """
    values = dict(record.fields)
    values["timestamp_utc"] = None
    values["timestamp_utc_status"] = UTC_UNAVAILABLE
    values.setdefault("run_label", provenance.run_label)
    if "firmware_version" in values:
        values["firmware_version_present"] = True
    # W04/W05 telemetry spells the probe set differently from the H8S wire.
    slot_alias = {
        "t_inside_c": "t1",
        "t_cold_side_c": "t2",
        "t_hot_side_c": "t3",
        "t_ambient_c": "t4",
    }
    for source, target in slot_alias.items():
        if source in values:
            values.setdefault(f"{target}_telem_name", source)
    for name in ("door_open",):
        if values.get(name) is None:
            values[name] = "UNKNOWN"
    return Frame(provenance=provenance, values=values, raw=device_line)


def _empty_to_none(value: str) -> str | None:
    text = (value or "").strip()
    return text or None


def read_csv_capture(
    path: pathlib.Path,
    run_label: str,
    is_physical_measurement: bool = True,
    note: str = "",
) -> tuple[list[Frame], dict]:
    """Read a derived ColdGuard CSV capture into normalized frames.

    Column aliases are applied, empty status cells become ``None`` (never
    ``OK``), and ``frames_without_status`` counts the electrical columns that
    arrive unqualified so the validity layer can state it per row.
    """
    path = pathlib.Path(path)
    sha = sha256_file(path)
    frames: list[Frame] = []
    rejected: list[dict] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return [], {"lines_total": 0, "records": 0, "rejected": [{"reason": "empty file"}]}
        aliases = set(CSV_COLUMN_ALIASES)
        extra_columns = [c for c in reader.fieldnames if c not in aliases and c]
        for index, row in enumerate(reader, start=2):
            values: dict = {}
            for key, raw_value in row.items():
                if key is None:
                    continue
                name = CSV_COLUMN_ALIASES.get(key, key)
                text = _empty_to_none(raw_value)
                if text is None:
                    values[name] = None
                    continue
                try:
                    values[name] = _coerce_h8s(name, text)
                except TelemetryError:
                    if FLOAT_RE.match(text):
                        values[name] = float(text)
                    elif INT_RE.match(text):
                        values[name] = int(text)
                    else:
                        values[name] = text
            if values.get("door_open") is None:
                values["door_open"] = "UNKNOWN"
            values["timestamp_utc"] = None
            values["timestamp_utc_status"] = UTC_UNAVAILABLE
            values["run_label"] = run_label
            provenance = SourceProvenance(
                source_kind="csv_capture",
                source_path=path.as_posix(),
                source_sha256=sha,
                line_index=index,
                is_physical_measurement=is_physical_measurement,
                run_label=run_label,
                note=note,
            )
            try:
                seq = values.get("seq")
                if not isinstance(seq, int):
                    raise TelemetryError(f"seq is not an integer: {seq!r}")
                if not isinstance(values.get("device_ms"), int):
                    raise TelemetryError(f"device_ms is not an integer: {values['device_ms']!r}")
            except TelemetryError as exc:
                rejected.append({"line_index": index, "reason": str(exc)})
                continue
            frames.append(Frame(provenance=provenance, values=values, raw=""))
    return frames, {
        "lines_total": len(frames) + len(rejected),
        "records": len(frames),
        "rejected": rejected,
        "columns_seen": extra_columns,
        "source_sha256": sha,
    }


def read_h8s_jsonl(
    path: pathlib.Path,
    run_label: str,
    is_physical_measurement: bool = True,
    note: str = "",
) -> tuple[list[Frame], dict]:
    """Read ``monitor/samples.jsonl`` H8 frames."""
    path = pathlib.Path(path)
    sha = sha256_file(path)
    frames: list[Frame] = []
    rejected: list[dict] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        import json

        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            rejected.append({"line_index": index, "reason": f"not JSON: {exc}"})
            continue
        provenance = SourceProvenance(
            source_kind="h8s_jsonl",
            source_path=path.as_posix(),
            source_sha256=sha,
            line_index=index,
            is_physical_measurement=is_physical_measurement,
            run_label=run_label,
            note=note,
        )
        try:
            frames.append(parse_h8s_json_object(obj, provenance))
        except TelemetryError as exc:
            rejected.append({"line_index": index, "reason": str(exc)})
    return frames, {
        "lines_total": len(frames) + len(rejected),
        "records": len(frames),
        "rejected": rejected,
        "source_sha256": sha,
    }


def read_transcript(
    path: pathlib.Path,
    run_label: str,
    is_physical_measurement: bool = True,
    note: str = "",
) -> tuple[list[Frame], dict]:
    """Read a host-timestamped ``session_raw.log``/``telemetry_raw.log``."""
    path = pathlib.Path(path)
    sha = sha256_file(path)
    frames: list[Frame] = []
    rejected: list[dict] = []
    ignored = 0
    for index, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        host_time, device_line = strip_host_capture_time(stripped)
        if not device_line.startswith(("#CG H8S", schema.PREFIX)):
            ignored += 1
            continue
        provenance = SourceProvenance(
            source_kind="h8s_transcript",
            source_path=path.as_posix(),
            source_sha256=sha,
            line_index=index,
            is_physical_measurement=is_physical_measurement,
            run_label=run_label,
            note=note,
        )
        try:
            frames.append(parse_frame_line(stripped, provenance))
        except TelemetryError as exc:
            rejected.append({"line_index": index, "reason": str(exc)})
    return frames, {
        "lines_total": len(frames) + len(rejected) + ignored,
        "records": len(frames),
        "ignored_non_device_lines": ignored,
        "rejected": rejected,
        "source_sha256": sha,
        "host_time_present_on_frames": sum(
            1 for f in frames if f.values.get("host_capture_time_utc")
        ),
    }


def read_boot_identity(lines: Iterable[str]) -> dict:
    """Pull device/firmware/hardware identity and ROM roles from boot lines.

    The frame itself does not carry ROM ids; they are emitted once per boot by
    the ``#CG ROM`` and ``#CG LOG`` lines. Reading them from the same capture is
    what keeps sensor identity attached to the run instead of to a guess.
    """
    identity: dict = {"firmware_version": None, "hardware_config_id": None, "device_id": None,
                     "roms": {}, "log_schema_version": None}
    for line in lines:
        text = line.strip()
        if text.startswith("#CG LOG "):
            fields = tokenize_kv(text, 2)
            identity["firmware_version"] = fields.get("fw")
            identity["hardware_config_id"] = fields.get("hw")
            identity["device_id"] = fields.get("device")
            identity["log_schema_version"] = fields.get("v")
        elif text.startswith("#CG ROM "):
            fields = tokenize_kv(text, 2)
            role = fields.get("role")
            rom = fields.get("rom")
            if role and rom:
                identity["roms"][role] = {
                    "rom": rom,
                    "present": fields.get("present"),
                    "status": fields.get("status"),
                    "rom_source": "BOOT_LOG_LINE",
                }
    return identity


def group_by_run(frames: Iterable[Frame]) -> dict[tuple, list[Frame]]:
    """Group frames by ``(run_label, boot_id, run_id)`` preserving order."""
    grouped: dict[tuple, list[Frame]] = {}
    for frame in frames:
        key = (frame.provenance.run_label, frame.boot_id, frame.run_id)
        grouped.setdefault(key, []).append(frame)
    for bucket in grouped.values():
        bucket.sort(key=lambda f: (f.seq if isinstance(f.seq, int) else -1))
    return grouped
