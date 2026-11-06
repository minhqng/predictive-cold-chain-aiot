"""W04 source-aware analytical intake (B-W04-01 and B-W04-05).

Three concepts stay separate, by construction:

* **source representation** — what a producer emitted (A's W09 run export,
  C's telemetry-v1 JSON envelope, the firmware serial encodings). Each
  representation keeps its own version namespace; a serial ``schema=3`` is
  not a backend ``schema_version=1``.
* **normalized analytical representation** — the stable B-facing identity,
  time, quality, role and measurement fields in :class:`Capture` /
  :class:`NormalizedRow`.
* **scientific eligibility** — the explicitly gated admission ladder in
  :func:`evaluate_admission`. A successful parse never implies admission.

The module deliberately does **not** implement a serial-to-MQTT gateway, a
database, a run validator (W08) or a telemetry QA pipeline (W05). Raw
``#CG H8S`` / ``#CG TELEM`` lines are recognized and refused with a precise
reason: B consumes A's evidence-grade export, not the producer stream.

Fail-closed rules enforced here (W04 contract):

* no invented device UTC, calibration id, hardware configuration id, run id,
  sensor ROM, physical position or role;
* host capture time is a separate domain and is never written into event
  time;
* uptime is boot-scoped and never treated as a global clock;
* a hot-side probe never enters a chamber-air aggregate;
* a missing electrical value stays ``None`` and is distinct from a measured
  ``0.0``;
* A's invalidation ledger is authoritative — plausible-looking readings do
  not re-validate a run;
* missing physical-validity evidence never produces a predictive admission;
* synthetic fixtures never become physical measurements through conversion.
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from .observations import Observation, parse_event_time, validate_observation

__all__ = [
    "AValidityEvidence",
    "AdmissionResult",
    "AdmissionStage",
    "AdmissionStatus",
    "Blocker",
    "Capture",
    "DatasetReadiness",
    "IndependentRunCount",
    "NormalizedRow",
    "ProbeReading",
    "RoleError",
    "RunIdentity",
    "ScenarioAdmission",
    "SensorRole",
    "SourceIdentity",
    "SourceRefusal",
    "TimeSemantics",
    "chamber_air_mean",
    "classify_source",
    "count_independent_runs",
    "detect_source_format",
    "evaluate_admission",
    "load_a_run_index",
    "load_capture",
    "summarize_readiness",
]

SOURCE_FORMAT_A_W09_EXPORT = "a-w09-run-export-v2"
SOURCE_FORMAT_C_TELEMETRY_V1 = "c-telemetry-json-v1"
SOURCE_FORMAT_H8S_SERIAL_V3 = "firmware-h8s-serial-v3"
SOURCE_FORMAT_TELEM_SERIAL = "firmware-telem-serial"
SOURCE_FORMAT_A_COMPANION_CSV = "a-w09-companion-csv"
SOURCE_FORMAT_UNKNOWN = "unknown"

SCHEMA_NAMESPACE_A = "w09-run-export/v2"
SCHEMA_NAMESPACE_C = "coldguard.telemetry/v1"
SCHEMA_NAMESPACE_H8S = "coldguard.h8s-serial/v3"
SCHEMA_NAMESPACE_TELEM = "coldguard.telem-serial/v1-3"

A_W09_EXPORT_VERSION = "w09-run-export-v2"
A_RUN_INDEX_VERSION = "w09-run-index-v1"

TIME_EVENT_UTC = "EVENT_UTC"
TIME_BOOT_SCOPED_UPTIME = "BOOT_SCOPED_UPTIME"
TIME_NONE = "NONE"

PROVENANCE_PHYSICAL = "PHYSICAL"
PROVENANCE_SYNTHETIC = "SYNTHETIC"
PROVENANCE_NON_PHYSICAL = "NON_PHYSICAL"
PROVENANCE_UNVERIFIED = "UNVERIFIED"

QUALITY_VALUES = ("VALID", "DEGRADED", "INVALID", "UNKNOWN")
DOOR_STATES = ("OPEN", "CLOSED", "UNKNOWN")
COOLING_STATES = ("ON", "OFF")

# Mirror of Doc 02 §14.3 / Doc 00 §3.2; duplicated intentionally so the ML
# package has no import dependency on the backend.
LEGACY_FORBIDDEN_KEYS = frozenset(
    {
        "current_1",
        "current_2",
        "power_1",
        "power_2",
        "cmd_1",
        "cmd_2",
        "ina226",
        "tec_2",
        "second_tec",
    }
)

B_RUN_ID_PATTERN = re.compile(r"^CG-S\d+-[A-Za-z0-9]+-[A-Za-z0-9]+$")
ROM_PATTERN = re.compile(r"^[0-9A-Fa-f]{16}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

KNOWN_SLOTS = ("t1", "t2", "t3", "t4")
CHAMBER_AIR_POSITIONS = frozenset(
    {"CHAMBER_CENTER", "CHAMBER_BOTTOM", "CHAMBER_NEAR_DOOR"}
)
NON_AIR_POSITIONS = frozenset({"TEC_HOT_SIDE"})
DEVICE_HOT_SIDE_TOKENS = frozenset({"HOT_SIDE", "TEC_HOT_SIDE"})

A_REQUIRED_EXPORT_FIELDS = (
    "run_id",
    "run_id_status",
    "boot_id",
    "boot_id_status",
    "device_id",
    "hardware_config_id",
    "firmware_version",
    "schema_version",
    "scenario_candidate",
    "experiment_phase",
    "sensors",
    "timestamp_semantics",
    "uptime_semantics",
    "cadence",
    "frames",
    "row_contract",
    "per_field_quality",
    "invalidation",
    "derived_thermal_states",
    "provenance",
    "is_physical_measurement",
    "status_label",
    "export_version",
)
A_REQUIRED_SENSOR_FIELDS = (
    "raw_slot",
    "rom",
    "rom_source",
    "physical_position",
    "position_source",
    "raw_role_in_capture",
    "in_chamber_air_mean",
)
A_REQUIRED_ROW_COLUMNS = (
    "seq",
    "run_id",
    "boot_id",
    "device_id",
    "hardware_config_id",
    "firmware_version",
    "device_ms",
    "timestamp_utc",
    "timestamp_utc_status",
    "host_capture_time_utc",
    "invalidation_reasons",
    "experiment_phase",
    "quality",
    "usable_for",
    "t1",
    "t2",
    "t3",
    "t4",
    "door_open",
    "door_polarity",
    "voltage_v",
    "current_a",
    "power_w",
    "energy_wh",
)

NOT_AVAILABLE = "NOT_AVAILABLE"
NOT_CARRIED_DEVICE_ID = "NOT_CARRIED_BY_THIS_ENCODING"


class SourceRefusal(ValueError):
    """A source cannot be mapped without guessing; the code names why."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class RoleError(ValueError):
    """A role-dependent computation was requested with unknown/foreign roles."""


class AdmissionStage(str, Enum):
    """Cumulative admission ladder; ``EXCLUDED_OR_BLOCKED`` is terminal."""

    SOURCE_RECOGNIZED = "SOURCE_RECOGNIZED"
    STRUCTURALLY_VALID = "STRUCTURALLY_VALID"
    USABLE_FOR_DIAGNOSTIC_QA = "USABLE_FOR_DIAGNOSTIC_QA"
    PHYSICALLY_QUALIFIED = "PHYSICALLY_QUALIFIED"
    ELIGIBLE_FOR_PREDICTIVE_DATASET = "ELIGIBLE_FOR_PREDICTIVE_DATASET"
    EXCLUDED_OR_BLOCKED = "EXCLUDED_OR_BLOCKED"


AdmissionStatus = AdmissionStage


@dataclass(frozen=True)
class Blocker:
    code: str
    stage: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "stage": self.stage, "detail": self.detail}


@dataclass(frozen=True)
class SourceIdentity:
    path: str
    sha256: str
    format: str
    schema_namespace: str
    provenance: str
    is_physical_measurement: bool | None
    pinned_sources: tuple[tuple[str, str | None, bool | None], ...] = ()
    companion_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "format": self.format,
            "schema_namespace": self.schema_namespace,
            "provenance": self.provenance,
            "is_physical_measurement": self.is_physical_measurement,
            "companion_sha256": self.companion_sha256,
            "pinned_sources": [
                {"path": path, "sha256": digest, "exists": exists}
                for path, digest, exists in self.pinned_sources
            ],
        }


@dataclass(frozen=True)
class TimeSemantics:
    domain: str
    event_time_status: str
    clock_sync: str
    boot_scoped: bool
    cross_boot_join_allowed: bool
    absolute_latency_supported: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "event_time_status": self.event_time_status,
            "clock_sync": self.clock_sync,
            "boot_scoped": self.boot_scoped,
            "cross_boot_join_allowed": self.cross_boot_join_allowed,
            "absolute_latency_supported": self.absolute_latency_supported,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RunIdentity:
    run_id: str | None
    run_id_status: str
    run_ids: tuple[str, ...]
    boot_id: str | None
    boot_id_status: str
    device_id: str | None
    device_id_status: str
    hardware_config_id: str | None
    hardware_config_status: str
    firmware_version: str | None
    firmware_version_status: str
    calibration_id: str | None
    calibration_status: str
    scenario_id: str | None
    scenario_status: str
    controller_id: str | None
    controller_status: str
    device_run_label: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_id_status": self.run_id_status,
            "run_ids": list(self.run_ids),
            "boot_id": self.boot_id,
            "boot_id_status": self.boot_id_status,
            "device_id": self.device_id,
            "device_id_status": self.device_id_status,
            "hardware_config_id": self.hardware_config_id,
            "hardware_config_status": self.hardware_config_status,
            "firmware_version": self.firmware_version,
            "firmware_version_status": self.firmware_version_status,
            "calibration_id": self.calibration_id,
            "calibration_status": self.calibration_status,
            "scenario_id": self.scenario_id,
            "scenario_status": self.scenario_status,
            "controller_id": self.controller_id,
            "controller_status": self.controller_status,
            "device_run_label": self.device_run_label,
        }


@dataclass(frozen=True)
class SensorRole:
    slot: str
    rom: str | None
    rom_source: str | None
    rom_readback_verified: bool | None
    physical_position: str | None
    position_source: str | None
    in_chamber_air_aggregate: bool | None
    exclusion_reason: str | None
    raw_roles: tuple[str, ...]
    role_conflict: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "rom": self.rom,
            "rom_source": self.rom_source,
            "rom_readback_verified": self.rom_readback_verified,
            "physical_position": self.physical_position,
            "position_source": self.position_source,
            "in_chamber_air_aggregate": self.in_chamber_air_aggregate,
            "exclusion_reason": self.exclusion_reason,
            "raw_roles": list(self.raw_roles),
            "role_conflict": self.role_conflict,
        }


@dataclass(frozen=True)
class ProbeReading:
    slot: str
    value_c: float | None
    status: str | None
    role: str | None
    age_ms: int | None
    rom: str | None
    physical_position: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "value_c": self.value_c,
            "status": self.status,
            "role": self.role,
            "age_ms": self.age_ms,
            "rom": self.rom,
            "physical_position": self.physical_position,
        }


@dataclass(frozen=True)
class NormalizedRow:
    seq: int
    boot_id: str
    run_id: str | None
    device_id: str | None
    hardware_config_id: str | None
    firmware_version: str | None
    device_ms: int | None
    event_time_utc: _dt.datetime | None
    host_capture_time_utc: _dt.datetime | None
    probes: tuple[ProbeReading, ...]
    t_air_c: float | None
    rh_pct: float | None
    pressure_hpa: float | None
    door_state: str
    door_polarity: str | None
    cooling_voltage_v: float | None
    cooling_current_a: float | None
    cooling_power_w: float | None
    cooling_energy_counter_wh: float | None
    electrical_measured_fields: tuple[str, ...]
    applied_cooling: str | None
    applied_duty: float | None
    applied_duty_permille: int | None
    requested_duty_permille: int | None
    readback_duty_permille: int | None
    device_state: str | None
    experiment_phase: str | None
    quality: tuple[tuple[str, str], ...]
    overall_quality: str | None
    producer_quality: str | None
    usable_for: tuple[str, ...]
    invalidation_reasons: tuple[str, ...]
    source_line_index: int | None
    dedup_key: tuple[str, ...]

    def probe(self, slot: str) -> ProbeReading:
        for reading in self.probes:
            if reading.slot == slot:
                return reading
        raise KeyError(f"slot {slot!r} is not carried by this row")

    @property
    def t1_c(self) -> float | None:
        return self.probe("t1").value_c

    @property
    def t2_c(self) -> float | None:
        return self.probe("t2").value_c

    @property
    def t3_c(self) -> float | None:
        return self.probe("t3").value_c

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "boot_id": self.boot_id,
            "run_id": self.run_id,
            "device_id": self.device_id,
            "hardware_config_id": self.hardware_config_id,
            "firmware_version": self.firmware_version,
            "device_ms": self.device_ms,
            "event_time_utc": _time_to_text(self.event_time_utc),
            "host_capture_time_utc": _time_to_text(self.host_capture_time_utc),
            "probes": [probe.to_dict() for probe in self.probes],
            "t_air_c": self.t_air_c,
            "rh_pct": self.rh_pct,
            "pressure_hpa": self.pressure_hpa,
            "door_state": self.door_state,
            "door_polarity": self.door_polarity,
            "cooling_voltage_v": self.cooling_voltage_v,
            "cooling_current_a": self.cooling_current_a,
            "cooling_power_w": self.cooling_power_w,
            "cooling_energy_counter_wh": self.cooling_energy_counter_wh,
            "electrical_measured_fields": list(self.electrical_measured_fields),
            "applied_cooling": self.applied_cooling,
            "applied_duty": self.applied_duty,
            "applied_duty_permille": self.applied_duty_permille,
            "requested_duty_permille": self.requested_duty_permille,
            "readback_duty_permille": self.readback_duty_permille,
            "device_state": self.device_state,
            "experiment_phase": self.experiment_phase,
            "quality": dict(self.quality),
            "overall_quality": self.overall_quality,
            "producer_quality": self.producer_quality,
            "usable_for": list(self.usable_for),
            "invalidation_reasons": list(self.invalidation_reasons),
            "source_line_index": self.source_line_index,
            "dedup_key": list(self.dedup_key),
        }


@dataclass(frozen=True)
class AValidityEvidence:
    source: str
    is_valid: bool | None
    status: str
    reasons: tuple[str, ...]
    rows_usable_per_scenario: tuple[tuple[str, int], ...]
    required_domains: tuple[tuple[str, tuple[str, ...]], ...]
    reason_counts: tuple[tuple[str, int], ...]
    rows_total: int | None
    usable_fraction: float | None
    hardware_config_verified: bool | None
    calibration_verified: bool | None
    clock_sync_verified: bool | None
    valid_scenarios: tuple[str, ...] = ()

    @property
    def rows_by_scenario(self) -> dict[str, int]:
        return dict(self.rows_usable_per_scenario)

    @property
    def domains_by_scenario(self) -> dict[str, tuple[str, ...]]:
        return dict(self.required_domains)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "is_valid": self.is_valid,
            "status": self.status,
            "reasons": list(self.reasons),
            "rows_usable_per_scenario": dict(self.rows_usable_per_scenario),
            "required_domains": {
                scenario: list(domains)
                for scenario, domains in self.required_domains
            },
            "reason_counts": dict(self.reason_counts),
            "rows_total": self.rows_total,
            "usable_fraction": self.usable_fraction,
            "hardware_config_verified": self.hardware_config_verified,
            "calibration_verified": self.calibration_verified,
            "clock_sync_verified": self.clock_sync_verified,
            "valid_scenarios": list(self.valid_scenarios),
        }


@dataclass(frozen=True)
class Capture:
    source: SourceIdentity
    run: RunIdentity
    time: TimeSemantics
    rows: tuple[NormalizedRow, ...]
    sensors: tuple[SensorRole, ...]
    a_validity: AValidityEvidence | None
    declared_unavailable_fields: tuple[str, ...] = ()
    recognized_fields: tuple[str, ...] = ()
    unknown_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def sensor(self, slot: str) -> SensorRole:
        for role in self.sensors:
            if role.slot == slot:
                return role
        raise KeyError(f"no role record for slot {slot!r}")

    @property
    def chamber_air_slots(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                role.slot
                for role in self.sensors
                if role.in_chamber_air_aggregate is True
                and role.physical_position in CHAMBER_AIR_POSITIONS
            )
        )

    @property
    def hot_side_slots(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                role.slot
                for role in self.sensors
                if role.physical_position in NON_AIR_POSITIONS
            )
        )

    @property
    def unknown_role_slots(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                role.slot
                for role in self.sensors
                if role.rom is None
                or role.physical_position is None
                or role.in_chamber_air_aggregate is None
                or role.role_conflict is not None
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "run": self.run.to_dict(),
            "time": self.time.to_dict(),
            "rows": len(self.rows),
            "sensors": [role.to_dict() for role in self.sensors],
            "a_validity": None if self.a_validity is None else self.a_validity.to_dict(),
            "declared_unavailable_fields": list(self.declared_unavailable_fields),
            "recognized_fields": list(self.recognized_fields),
            "unknown_fields": list(self.unknown_fields),
            "warnings": list(self.warnings),
            "chamber_air_slots": list(self.chamber_air_slots),
            "hot_side_slots": list(self.hot_side_slots),
            "unknown_role_slots": list(self.unknown_role_slots),
        }


@dataclass(frozen=True)
class ScenarioAdmission:
    scenario_id: str
    eligible: bool
    eligible_rows: int
    required_domains: tuple[str, ...]
    blockers: tuple[Blocker, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "eligible": self.eligible,
            "eligible_rows": self.eligible_rows,
            "required_domains": list(self.required_domains),
            "blockers": [blocker.to_dict() for blocker in self.blockers],
        }


@dataclass(frozen=True)
class AdmissionResult:
    status: AdmissionStage
    highest_stage: AdmissionStage
    blockers: tuple[Blocker, ...]
    scenarios: tuple[ScenarioAdmission, ...]
    eligible_s1_runs: int
    eligible_s2_runs: int
    predictive_dataset_readiness: str
    capture: Capture

    @property
    def eligible(self) -> bool:
        return self.status is AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "highest_stage": self.highest_stage.value,
            "eligible": self.eligible,
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
            "eligible_s1_runs": self.eligible_s1_runs,
            "eligible_s2_runs": self.eligible_s2_runs,
            "predictive_dataset_readiness": self.predictive_dataset_readiness,
        }


@dataclass(frozen=True)
class IndependentRunCount:
    unique_physical_sources: int
    duplicate_views: int
    detail: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "unique_physical_sources": self.unique_physical_sources,
            "duplicate_views": self.duplicate_views,
            "detail": [dict(item) for item in self.detail],
        }


@dataclass(frozen=True)
class DatasetReadiness:
    eligible_s1_runs: int
    eligible_s2_runs: int
    predictive_dataset_readiness: str
    unique_physical_sources: int
    duplicate_views: int
    exclusions: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible_s1_runs": self.eligible_s1_runs,
            "eligible_s2_runs": self.eligible_s2_runs,
            "predictive_dataset_readiness": self.predictive_dataset_readiness,
            "unique_physical_sources": self.unique_physical_sources,
            "duplicate_views": self.duplicate_views,
            "exclusions": [dict(item) for item in self.exclusions],
        }


# ---------------------------------------------------------------------------
# source detection and classification
# ---------------------------------------------------------------------------


def detect_source_format(source: str | Path) -> str:
    """Identify a supported representation or refuse without mapping fields."""
    path = _require_source_path(source)
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise SourceRefusal(
                "SOURCE_NOT_AN_OBJECT",
                f"{_display_path(path)}: top-level JSON value is "
                f"{type(payload).__name__}, not a mapping",
            )
        if "export_version" in payload:
            version = payload.get("export_version")
            if version == A_W09_EXPORT_VERSION:
                return SOURCE_FORMAT_A_W09_EXPORT
            raise SourceRefusal(
                "UNSUPPORTED_SOURCE_VERSION",
                f"{_display_path(path)}: unsupported A export version {version!r}; "
                f"supported: {A_W09_EXPORT_VERSION!r}",
            )
        if _looks_like_c_telemetry(payload):
            version = payload.get("schema_version")
            if type(version) is int and version == 1:
                return SOURCE_FORMAT_C_TELEMETRY_V1
            raise SourceRefusal(
                "UNSUPPORTED_SOURCE_VERSION",
                f"{_display_path(path)}: unsupported C telemetry schema_version "
                f"{version!r}; supported: 1 (coldguard.telemetry/v1)",
            )
        raise SourceRefusal(
            "UNRECOGNIZED_SOURCE_FORMAT",
            f"{_display_path(path)}: JSON is neither a W09 run export "
            f"({A_W09_EXPORT_VERSION}) nor a C telemetry-v1 payload; no field "
            "mapping is attempted",
        )
    if suffix == ".csv":
        header = _read_csv_header(path)
        required = {"seq", "run_id", "boot_id", "device_ms", "t1", "t2", "t3"}
        if required <= set(header):
            return SOURCE_FORMAT_A_COMPANION_CSV
        raise SourceRefusal(
            "UNRECOGNIZED_SOURCE_FORMAT",
            f"{_display_path(path)}: CSV is not an A W09 companion row-validity "
            "table; no column mapping is guessed",
        )
    first = _first_content_line(path)
    if first.startswith("#CG H8S"):
        return SOURCE_FORMAT_H8S_SERIAL_V3
    if first.startswith("#CG TELEM"):
        return SOURCE_FORMAT_TELEM_SERIAL
    raise SourceRefusal(
        "UNRECOGNIZED_SOURCE_FORMAT",
        f"{_display_path(path)}: first content line is not a recognized device "
        "encoding; no field mapping is attempted",
    )


def classify_source(source: str | Path) -> dict[str, Any]:
    """Deterministic identification report (no structural validation)."""
    path = _require_source_path(source)
    try:
        fmt = detect_source_format(path)
    except SourceRefusal as exc:
        return {
            "source_path": _display_path(path),
            "sha256": _sha256_file(path),
            "source_format": SOURCE_FORMAT_UNKNOWN,
            "schema_namespace": None,
            "supported": False,
            "reason_code": exc.code,
            "reason": exc.detail,
        }
    namespace = {
        SOURCE_FORMAT_A_W09_EXPORT: SCHEMA_NAMESPACE_A,
        SOURCE_FORMAT_C_TELEMETRY_V1: SCHEMA_NAMESPACE_C,
        SOURCE_FORMAT_H8S_SERIAL_V3: SCHEMA_NAMESPACE_H8S,
        SOURCE_FORMAT_TELEM_SERIAL: SCHEMA_NAMESPACE_TELEM,
        SOURCE_FORMAT_A_COMPANION_CSV: "w09-run-export/v2/companion",
    }.get(fmt)
    supported = fmt in {
        SOURCE_FORMAT_A_W09_EXPORT,
        SOURCE_FORMAT_C_TELEMETRY_V1,
    }
    reason = (
        "supported analytical source"
        if supported
        else (
            "recognized producer representation; B/W04 consumes A's W09 run "
            "export and does not implement a serial gateway"
            if fmt in {SOURCE_FORMAT_H8S_SERIAL_V3, SOURCE_FORMAT_TELEM_SERIAL}
            else "companion CSV lacks run metadata and A validity; supply the "
            "W09 export JSON"
        )
    )
    return {
        "source_path": _display_path(path),
        "sha256": _sha256_file(path),
        "source_format": fmt,
        "schema_namespace": namespace,
        "supported": supported,
        "reason_code": None if supported else "SOURCE_FORMAT_NOT_ANALYTICAL",
        "reason": reason,
    }


def load_capture(
    source: str | Path,
    *,
    source_format: str = "auto",
    a_run_index: str | Path | None = None,
) -> Capture:
    """Load one supported source into the normalized analytical model.

    ``a_run_index`` is required for physical qualification of an A export:
    without it the export's own summary is recorded, but the absence of an
    authoritative A verdict is a blocker, never a silent pass.
    """
    path = _require_source_path(source)
    detected = detect_source_format(path)
    if source_format not in ("auto", None):
        if source_format != detected:
            raise SourceRefusal(
                "SOURCE_FORMAT_MISMATCH",
                f"{_display_path(path)}: requested source format {source_format!r} "
                f"but detected {detected!r}",
            )
    if detected == SOURCE_FORMAT_A_W09_EXPORT:
        return _load_a_w09_export(path, a_run_index=a_run_index)
    if detected == SOURCE_FORMAT_C_TELEMETRY_V1:
        return _load_c_telemetry(path)
    if detected == SOURCE_FORMAT_H8S_SERIAL_V3:
        raise SourceRefusal(
            "SERIAL_SCHEMA_NOT_BACKEND_WIRE",
            f"{_display_path(path)}: firmware '#CG H8S schema=3' is a producer "
            "serial representation with its own namespace; it is not the C "
            "telemetry-json schema_version=1 namespace. B/W04 does not implement "
            "a serial-to-analytical gateway; consume A's W09 run export instead.",
        )
    if detected == SOURCE_FORMAT_TELEM_SERIAL:
        raise SourceRefusal(
            "SERIAL_SCHEMA_NOT_BACKEND_WIRE",
            f"{_display_path(path)}: '#CG TELEM' is a firmware serial line, not "
            "a C MQTT JSON telemetry document; no cross-namespace mapping is "
            "attempted",
        )
    if detected == SOURCE_FORMAT_A_COMPANION_CSV:
        raise SourceRefusal(
            "COMPANION_METADATA_MISSING",
            f"{_display_path(path)}: an A companion row-validity CSV carries rows "
            "but not the run metadata, timestamp semantics, sensor roles or A "
            "validity summary; supply the W09 export JSON that references it",
        )
    raise SourceRefusal(
        "UNRECOGNIZED_SOURCE_FORMAT",
        f"{_display_path(path)}: no supported source adapter",
    )


# ---------------------------------------------------------------------------
# A W09 run export adapter
# ---------------------------------------------------------------------------


def _load_a_w09_export(path: Path, *, a_run_index: str | Path | None) -> Capture:
    payload = _read_json(path)
    assert isinstance(payload, dict)
    _reject_legacy_keys(payload, path)
    missing = [name for name in A_REQUIRED_EXPORT_FIELDS if name not in payload]
    if missing:
        raise SourceRefusal(
            "A_EXPORT_INCOMPLETE",
            f"{_display_path(path)}: missing required export fields {missing}",
        )
    boolean_physical = payload.get("is_physical_measurement")
    if not isinstance(boolean_physical, bool):
        raise SourceRefusal(
            "A_EXPORT_INVALID",
            f"{_display_path(path)}: is_physical_measurement must be an explicit "
            f"boolean, got {boolean_physical!r}",
        )
    sensors = _parse_sensor_roles(payload["sensors"], path=path)
    roles_by_slot = {role.slot: role for role in sensors}
    if len(roles_by_slot) != len(sensors):
        raise SourceRefusal(
            "A_EXPORT_INVALID",
            f"{_display_path(path)}: duplicate sensor slots in the sensors block",
        )

    run = _parse_a_run_identity(payload)
    frames_block = payload["frames"]
    if not isinstance(frames_block, dict):
        raise SourceRefusal(
            "A_EXPORT_INVALID",
            f"{_display_path(path)}: frames must be a mapping with companion "
            f"metadata, got {type(frames_block).__name__}",
        )
    companion_rel = frames_block.get("companion_file")
    if not isinstance(companion_rel, str) or not companion_rel.strip():
        raise SourceRefusal(
            "A_EXPORT_INVALID",
            f"{_display_path(path)}: frames.companion_file is required",
        )
    companion_path = _resolve_companion(path, companion_rel)
    if companion_path is None:
        raise SourceRefusal(
            "COMPANION_FILE_MISSING",
            f"{_display_path(path)}: companion_file {companion_rel!r} was not "
            "found beside the export, at the dossier root, or at the repository "
            "root; no path is guessed",
        )
    declared_columns = frames_block.get("columns_per_row")
    if not isinstance(declared_columns, list) or not all(
        isinstance(item, str) for item in declared_columns
    ):
        raise SourceRefusal(
            "A_EXPORT_INVALID",
            f"{_display_path(path)}: frames.columns_per_row must be a string list",
        )
    header = _read_csv_header(companion_path)
    legacy_columns = sorted(
        {column.lower() for column in header} & LEGACY_FORBIDDEN_KEYS
    )
    if legacy_columns:
        raise SourceRefusal(
            "LEGACY_FORBIDDEN_FIELD",
            f"{_display_path(companion_path)}: legacy column(s) "
            f"{legacy_columns} are forbidden; ColdGuard P0 has one cooling "
            "branch and no INA226/second-TEC channel",
        )
    if header != declared_columns:
        raise SourceRefusal(
            "COMPANION_HEADER_MISMATCH",
            f"{_display_path(companion_path)}: header does not match "
            "frames.columns_per_row; the declaration and the delivered CSV "
            "disagree, so columns are not mapped",
        )
    missing_columns = [name for name in A_REQUIRED_ROW_COLUMNS if name not in header]
    if missing_columns:
        raise SourceRefusal(
            "A_ROW_CONTRACT_INCOMPLETE",
            f"{_display_path(companion_path)}: missing required row columns "
            f"{missing_columns}",
        )
    rows, row_warnings = _parse_a_rows(
        companion_path,
        header,
        run=run,
        roles_by_slot=roles_by_slot,
        expected_rows=frames_block.get("rows"),
    )
    time_semantics = _a_time_semantics(payload, rows, path)
    provenance = (
        PROVENANCE_PHYSICAL
        if boolean_physical
        else PROVENANCE_NON_PHYSICAL
    )
    pinned = _pinned_sources(payload.get("provenance"), path)
    export_validity = _a_validity_from_export(payload)
    validity = export_validity
    if a_run_index is not None:
        index = load_a_run_index(a_run_index)
        entry = _select_a_index_entry(index, run, path)
        validity = _a_validity_from_index(
            index, entry, run=run, source=str(a_run_index)
        )
        if not validity.required_domains:
            # The run index describes eligibility; the export summary carries
            # the scenario/domain map. Neither is invented: they come from A.
            validity = replace(
                validity, required_domains=export_validity.required_domains
            )
    row_contract = payload.get("row_contract")
    if not isinstance(row_contract, dict):
        raise SourceRefusal(
            "A_EXPORT_INVALID",
            f"{_display_path(path)}: row_contract must be a mapping",
        )
    unavailable = row_contract.get("not_available_per_row", {})
    declared_unavailable = tuple(sorted(unavailable)) if isinstance(unavailable, dict) else ()
    unknown_fields = tuple(sorted(set(header) - _a_known_columns()))
    warnings = list(row_warnings)
    if validity is not None and validity.source == "a-w09-export-summary":
        warnings.append(
            "A export summary is not an authoritative validity verdict; supply "
            "--a-run-index for physical qualification"
        )
    if any(exists is None for _, _digest, exists in pinned):
        warnings.append(
            "one or more pinned sources could not be verified against a "
            "repository checkout; physical qualification is blocked"
        )
    if run.run_id is None:
        warnings.append(
            f"run identity is not a single source-carried run_id "
            f"({run.run_id_status}); no run_id is fabricated"
        )
    if run.device_id is None:
        warnings.append(
            f"device identity is {run.device_id_status}; dedup identity is not "
            "cross-device safe"
        )
    return Capture(
        source=SourceIdentity(
            path=_display_path(path),
            sha256=_sha256_file(path),
            format=SOURCE_FORMAT_A_W09_EXPORT,
            schema_namespace=SCHEMA_NAMESPACE_A,
            provenance=provenance,
            is_physical_measurement=boolean_physical,
            pinned_sources=pinned,
            companion_sha256=_sha256_file(companion_path),
        ),
        run=run,
        time=time_semantics,
        rows=rows,
        sensors=sensors,
        a_validity=validity,
        declared_unavailable_fields=declared_unavailable,
        recognized_fields=tuple(header),
        unknown_fields=unknown_fields,
        warnings=tuple(warnings),
    )


def _a_known_columns() -> frozenset[str]:
    base = set(A_REQUIRED_ROW_COLUMNS)
    for slot in KNOWN_SLOTS:
        base.update(
            {
                f"{slot}_status",
                f"{slot}_role",
                f"{slot}_age_ms",
                f"{slot}_rom",
                f"{slot}_physical_position",
            }
        )
    base.update(
        {
            "source_path",
            "source_kind",
            "source_line_index",
            "dedup_key",
            "producer_quality",
            "thermal_quality",
            "environment_quality",
            "electrical_quality",
            "door_quality",
            "sequence_quality",
            "provenance_quality",
            "stage",
            "state",
            "stop_reason",
            "snapshot",
            "pwm_req_permille",
            "pwm_applied_permille",
            "pwm_readback_permille",
            "air_c",
            "rh_pct",
            "pressure_hpa",
        }
    )
    return frozenset(base)


def _parse_sensor_roles(raw: Any, *, path: Path) -> tuple[SensorRole, ...]:
    if not isinstance(raw, list) or not raw:
        raise SourceRefusal(
            "A_EXPORT_INVALID",
            f"{_display_path(path)}: sensors must be a non-empty list",
        )
    roles: list[SensorRole] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise SourceRefusal(
                "A_EXPORT_INVALID",
                f"{_display_path(path)}: sensors[{index}] is not a mapping",
            )
        missing = [name for name in A_REQUIRED_SENSOR_FIELDS if name not in entry]
        if missing:
            raise SourceRefusal(
                "A_SENSOR_BLOCK_INCOMPLETE",
                f"{_display_path(path)}: sensors[{index}] missing {missing}",
            )
        slot = str(entry["raw_slot"]).lower().strip()
        if slot in seen:
            raise SourceRefusal(
                "A_SENSOR_ROLE_CONTRADICTION",
                f"{_display_path(path)}: slot {slot!r} appears more than once",
            )
        seen.add(slot)
        rom = entry.get("rom")
        rom_value = str(rom).upper().strip() if rom not in (None, "") else None
        if rom_value is not None and not ROM_PATTERN.match(rom_value):
            raise SourceRefusal(
                "A_SENSOR_ROLE_CONTRADICTION",
                f"{_display_path(path)}: slot {slot!r} ROM {rom!r} is not a "
                "16-hex-digit DS18B20 identity",
            )
        position = entry.get("physical_position")
        if position in (None, "", "UNKNOWN", "NOT_AVAILABLE"):
            position_value = None
        else:
            position_value = str(position).upper().strip()
            if position_value not in (CHAMBER_AIR_POSITIONS | NON_AIR_POSITIONS):
                raise SourceRefusal(
                    "SENSOR_POSITION_UNKNOWN_VOCABULARY",
                    f"{_display_path(path)}: slot {slot!r} physical_position "
                    f"{position!r} is not in the frozen position vocabulary; an "
                    "unknown token is not silently dropped or treated as air",
                )
        in_air_raw = entry.get("in_chamber_air_mean")
        if not isinstance(in_air_raw, bool):
            raise SourceRefusal(
                "A_SENSOR_BLOCK_INCOMPLETE",
                f"{_display_path(path)}: slot {slot!r} in_chamber_air_mean must "
                f"be an explicit boolean, got {in_air_raw!r}",
            )
        raw_roles_raw = entry.get("raw_role_in_capture", [])
        if isinstance(raw_roles_raw, str):
            raw_roles = tuple(part for part in raw_roles_raw.split("|") if part)
        elif isinstance(raw_roles_raw, list):
            raw_roles = tuple(str(part) for part in raw_roles_raw if str(part) != "")
        else:
            raise SourceRefusal(
                "A_EXPORT_INVALID",
                f"{_display_path(path)}: slot {slot!r} raw_role_in_capture must "
                "be a list or pipe-delimited string",
            )
        role_conflict: str | None = None
        if in_air_raw is True and position_value in NON_AIR_POSITIONS:
            raise SourceRefusal(
                "HOT_SIDE_IN_CHAMBER_AIR",
                f"{_display_path(path)}: slot {slot!r} is "
                f"{position_value} but in_chamber_air_mean=true; a hot-side "
                "probe cannot enter a chamber-air aggregate",
            )
        if in_air_raw is True and position_value is None:
            raise SourceRefusal(
                "CHAMBER_AIR_ROLE_UNKNOWN",
                f"{_display_path(path)}: slot {slot!r} claims chamber-air "
                "membership without a known physical position",
            )
        if any(token.upper() in NON_AIR_POSITIONS for token in raw_roles) and in_air_raw:
            role_conflict = (
                "raw capture role says hot side but the frozen sensor block says "
                "chamber air"
            )
        roles.append(
            SensorRole(
                slot=slot,
                rom=rom_value,
                rom_source=_optional_text(entry.get("rom_source")),
                rom_readback_verified=(
                    entry.get("rom_readback_verified")
                    if isinstance(entry.get("rom_readback_verified"), bool)
                    else None
                ),
                physical_position=position_value,
                position_source=_optional_text(entry.get("position_source")),
                in_chamber_air_aggregate=in_air_raw,
                exclusion_reason=_optional_text(entry.get("exclusion_reason")),
                raw_roles=raw_roles,
                role_conflict=role_conflict,
            )
        )
    return tuple(sorted(roles, key=lambda role: role.slot))


def _parse_a_run_identity(payload: Mapping[str, Any]) -> RunIdentity:
    run_id_raw = payload.get("run_id")
    run_id = _optional_text(run_id_raw)
    run_status = str(payload.get("run_id_status", "NOT_CARRIED_BY_SOURCE"))
    run_ids_raw = payload.get("run_ids", [])
    run_ids: tuple[str, ...] = ()
    if isinstance(run_ids_raw, list):
        run_ids = tuple(str(item) for item in run_ids_raw if str(item).strip())
    if run_id is not None and run_id not in run_ids and run_ids:
        raise SourceRefusal(
            "RUN_ID_CONTRADICTION",
            f"run_id {run_id!r} is not present in run_ids {list(run_ids)}",
        )
    if run_status == "SOURCE_CARRIED_SINGLE" and len(run_ids) > 1:
        raise SourceRefusal(
            "RUN_ID_CONTRADICTION",
            f"run_id_status says a single run but run_ids carries "
            f"{list(run_ids)}",
        )
    if run_status != "SOURCE_CARRIED_SINGLE":
        # The status is authoritative: a non-single run id is not a lawful
        # dataset join key even when the payload still carries a string.
        run_id = None
    boot_raw = payload.get("boot_id")
    boot_id = _optional_text(boot_raw)
    boot_status = str(payload.get("boot_id_status", "NOT_CARRIED_BY_SOURCE"))
    boot_ids_raw = payload.get("boot_ids", [])
    boot_ids = (
        tuple(str(item) for item in boot_ids_raw if str(item).strip())
        if isinstance(boot_ids_raw, list)
        else ()
    )
    if boot_status == "SOURCE_CARRIED_SINGLE" and len(boot_ids) > 1:
        raise SourceRefusal(
            "BOOT_ID_CONTRADICTION",
            f"boot_id_status says a single boot but boot_ids carries "
            f"{list(boot_ids)}",
        )
    if boot_status != "SOURCE_CARRIED_SINGLE":
        boot_id = None
    device_raw = payload.get("device_id")
    if device_raw == NOT_CARRIED_DEVICE_ID:
        device_id = None
        device_status = NOT_CARRIED_DEVICE_ID
    else:
        device_id = _optional_text(device_raw)
        device_status = "CARRIED" if device_id is not None else "NOT_AVAILABLE"
    hardware_id = _optional_text(payload.get("hardware_config_id"))
    firmware = _optional_text(payload.get("firmware_version"))
    if firmware == NOT_CARRIED_DEVICE_ID:
        firmware = None
        firmware_status = NOT_CARRIED_DEVICE_ID
    else:
        firmware_status = "CARRIED" if firmware is not None else "NOT_AVAILABLE"
    scenario_candidate = _optional_text(payload.get("scenario_candidate"))
    scenario_id = None
    if scenario_candidate:
        match = re.match(r"^(S[1-6])(?:_|$)", scenario_candidate)
        if match:
            scenario_id = match.group(1)
    calibration_id = _optional_text(payload.get("calibration_id"))
    return RunIdentity(
        run_id=run_id,
        run_id_status=run_status,
        run_ids=run_ids,
        boot_id=boot_id,
        boot_id_status=boot_status,
        device_id=device_id,
        device_id_status=device_status,
        hardware_config_id=hardware_id,
        hardware_config_status=(
            "DECLARED_NOT_VERIFIED" if hardware_id is not None else "NOT_AVAILABLE"
        ),
        firmware_version=firmware,
        firmware_version_status=firmware_status,
        calibration_id=calibration_id,
        calibration_status=(
            "DECLARED_NOT_VERIFIED"
            if calibration_id is not None
            else "NOT_AVAILABLE"
        ),
        scenario_id=scenario_id,
        scenario_status=(
            "CANDIDATE_NOT_CERTIFIED" if scenario_id is not None else "NOT_AVAILABLE"
        ),
        controller_id=None,
        controller_status="NOT_CARRIED",
        device_run_label=_optional_text(payload.get("device_run_label")),
    )


def _parse_a_rows(
    companion_path: Path,
    header: list[str],
    *,
    run: RunIdentity,
    roles_by_slot: Mapping[str, SensorRole],
    expected_rows: Any,
) -> tuple[tuple[NormalizedRow, ...], tuple[str, ...]]:
    rows: list[NormalizedRow] = []
    warnings: list[str] = []
    previous_seq: dict[str, int] = {}
    previous_device_ms: dict[str, int] = {}
    seen_identity: set[tuple[str, str, int]] = set()
    seen_devices: set[str] = set()
    seen_hardware: set[str] = set()
    seen_firmware: set[str] = set()
    with companion_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != header:
            raise SourceRefusal(
                "COMPANION_HEADER_MISMATCH",
                f"{_display_path(companion_path)}: CSV reader header differs from "
                "the declared columns",
            )
        for line_index, raw_row in enumerate(reader, start=2):
            row = _parse_a_row(
                raw_row,
                line_index=line_index,
                run=run,
                roles_by_slot=roles_by_slot,
            )
            if row.run_id is not None:
                if run.run_id is not None and row.run_id != run.run_id:
                    raise SourceRefusal(
                        "RUN_ID_CONTRADICTION",
                        f"{_display_path(companion_path)}:{line_index}: row run_id "
                        f"{row.run_id!r} contradicts run-level run_id "
                        f"{run.run_id!r}",
                    )
                if run.run_id is None and run.run_ids and row.run_id not in run.run_ids:
                    raise SourceRefusal(
                        "RUN_ID_CONTRADICTION",
                        f"{_display_path(companion_path)}:{line_index}: row run_id "
                        f"{row.run_id!r} is not one of the source segments "
                        f"{list(run.run_ids)}",
                    )
                if run.run_id is None and not run.run_ids:
                    raise SourceRefusal(
                        "RUN_ID_CONTRADICTION",
                        f"{_display_path(companion_path)}:{line_index}: row carries "
                        f"run_id {row.run_id!r} but the export declares no run_ids",
                    )
            if run.boot_id is not None and row.boot_id != run.boot_id:
                raise SourceRefusal(
                    "BOOT_ID_CONTRADICTION",
                    f"{_display_path(companion_path)}:{line_index}: row boot_id "
                    f"{row.boot_id!r} contradicts run-level boot_id {run.boot_id!r}",
                )
            if (
                row.device_id is not None
                and run.device_id is not None
                and row.device_id != run.device_id
            ):
                raise SourceRefusal(
                    "DEVICE_ID_CONTRADICTION",
                    f"{_display_path(companion_path)}:{line_index}: row device_id "
                    f"{row.device_id!r} contradicts run-level device_id "
                    f"{run.device_id!r}",
                )
            if (
                row.hardware_config_id is not None
                and run.hardware_config_id is not None
                and row.hardware_config_id != run.hardware_config_id
            ):
                raise SourceRefusal(
                    "HARDWARE_CONFIG_CONTRADICTION",
                    f"{_display_path(companion_path)}:{line_index}: row "
                    f"hardware_config_id {row.hardware_config_id!r} contradicts "
                    f"the run-level {run.hardware_config_id!r}",
                )
            if (
                row.firmware_version is not None
                and run.firmware_version is not None
                and row.firmware_version != run.firmware_version
            ):
                raise SourceRefusal(
                    "FIRMWARE_VERSION_CONTRADICTION",
                    f"{_display_path(companion_path)}:{line_index}: row "
                    f"firmware_version {row.firmware_version!r} contradicts the "
                    f"run-level {run.firmware_version!r}",
                )
            if row.device_id is not None:
                seen_devices.add(row.device_id)
            if row.hardware_config_id is not None:
                seen_hardware.add(row.hardware_config_id)
            if row.firmware_version is not None:
                seen_firmware.add(row.firmware_version)
            identity = (
                row.device_id or NOT_CARRIED_DEVICE_ID,
                row.boot_id,
                row.seq,
            )
            if identity in seen_identity:
                raise SourceRefusal(
                    "SEQUENCE_CONTRADICTION",
                    f"{_display_path(companion_path)}:{line_index}: duplicate "
                    f"physical identity {identity}",
                )
            seen_identity.add(identity)
            if row.boot_id in previous_seq and row.seq <= previous_seq[row.boot_id]:
                raise SourceRefusal(
                    "SEQUENCE_CONTRADICTION",
                    f"{_display_path(companion_path)}:{line_index}: seq {row.seq} "
                    f"does not strictly increase within boot {row.boot_id!r}",
                )
            previous_seq[row.boot_id] = row.seq
            if row.device_ms is not None and row.boot_id in previous_device_ms:
                if row.device_ms < previous_device_ms[row.boot_id]:
                    raise SourceRefusal(
                        "SEQUENCE_CONTRADICTION",
                        f"{_display_path(companion_path)}:{line_index}: device_ms "
                        f"{row.device_ms} decreases within boot {row.boot_id!r}; "
                        "uptime is monotonic per boot",
                    )
            if row.device_ms is not None:
                previous_device_ms[row.boot_id] = row.device_ms
            rows.append(row)
    if len(seen_devices) > 1:
        raise SourceRefusal(
            "DEVICE_ID_CONTRADICTION",
            f"{_display_path(companion_path)}: rows carry multiple device ids "
            f"{sorted(seen_devices)} in one export",
        )
    if len(seen_hardware) > 1:
        raise SourceRefusal(
            "HARDWARE_CONFIG_CONTRADICTION",
            f"{_display_path(companion_path)}: rows carry multiple "
            f"hardware_config_id values {sorted(seen_hardware)} in one export",
        )
    if len(seen_firmware) > 1:
        raise SourceRefusal(
            "FIRMWARE_VERSION_CONTRADICTION",
            f"{_display_path(companion_path)}: rows carry multiple "
            f"firmware_version values {sorted(seen_firmware)} in one export",
        )
    if not rows:
        raise SourceRefusal(
            "EMPTY_CAPTURE",
            f"{_display_path(companion_path)}: no data rows",
        )
    if isinstance(expected_rows, int) and expected_rows != len(rows):
        raise SourceRefusal(
            "COMPANION_ROW_COUNT_MISMATCH",
            f"{_display_path(companion_path)}: {len(rows)} rows delivered but "
            f"the export declares {expected_rows}",
        )
    return tuple(rows), tuple(warnings)


def _parse_a_row(
    raw: Mapping[str, Any],
    *,
    line_index: int,
    run: RunIdentity,
    roles_by_slot: Mapping[str, SensorRole],
) -> NormalizedRow:
    seq = _required_int(raw.get("seq"), field="seq", context=f"row {line_index}")
    boot_id = _required_text(raw.get("boot_id"), field="boot_id", context=f"row {line_index}")
    row_run_id = _optional_text(raw.get("run_id"))
    row_device_id = _identity_text(raw.get("device_id"))
    row_hardware_id = _identity_text(raw.get("hardware_config_id"))
    row_firmware = _identity_text(raw.get("firmware_version"))
    device_ms = _optional_int(raw.get("device_ms"), field="device_ms", context=f"row {line_index}")
    event_time_raw = _optional_text(raw.get("timestamp_utc"))
    try:
        event_time = (
            None
            if event_time_raw is None
            else parse_event_time(event_time_raw, context=f"row {line_index} timestamp_utc")
        )
    except Exception as exc:
        raise SourceRefusal(
            "NAIVE_TIMESTAMP_OR_INVALID_TIME",
            f"row {line_index} timestamp_utc: {exc}",
        ) from exc
    timestamp_status = _optional_text(raw.get("timestamp_utc_status"))
    host_time_raw = _optional_text(raw.get("host_capture_time_utc"))
    try:
        host_time = (
            None
            if host_time_raw is None
            else parse_event_time(
                host_time_raw, context=f"row {line_index} host_capture_time_utc"
            )
        )
    except Exception as exc:
        raise SourceRefusal(
            "NAIVE_TIMESTAMP_OR_INVALID_TIME",
            f"row {line_index} host_capture_time_utc: {exc}",
        ) from exc
    if event_time is not None and timestamp_status in ("UNAVAILABLE", NOT_AVAILABLE):
        raise SourceRefusal(
            "TIME_SEMANTICS_CONTRADICTION",
            f"row {line_index}: a UTC timestamp is present while "
            f"timestamp_utc_status={timestamp_status!r}",
        )
    probes: list[ProbeReading] = []
    for slot in KNOWN_SLOTS:
        value = _optional_float(raw.get(slot), field=slot, context=f"row {line_index}")
        probe_role = _optional_text(raw.get(f"{slot}_role"))
        physical_position = _optional_text(raw.get(f"{slot}_physical_position"))
        rom = _optional_text(raw.get(f"{slot}_rom"))
        role = roles_by_slot.get(slot)
        if role is not None:
            if (
                probe_role is not None
                and probe_role.upper() in DEVICE_HOT_SIDE_TOKENS
                and role.in_chamber_air_aggregate is True
            ):
                raise SourceRefusal(
                    "SENSOR_ROLE_CONTRADICTION",
                    f"row {line_index}: slot {slot} raw role {probe_role!r} "
                    "says hot side but the sensor block says chamber air",
                )
            if (
                rom is not None
                and role.rom is not None
                and rom.upper() != role.rom.upper()
            ):
                raise SourceRefusal(
                    "SENSOR_ROM_CONTRADICTION",
                    f"row {line_index}: slot {slot} ROM {rom!r} contradicts the "
                    f"sensor block {role.rom!r}",
                )
            if (
                physical_position is not None
                and role.physical_position is not None
                and physical_position.upper() != role.physical_position
            ):
                raise SourceRefusal(
                    "SENSOR_POSITION_CONTRADICTION",
                    f"row {line_index}: slot {slot} position {physical_position!r} "
                    f"contradicts the sensor block {role.physical_position!r}",
                )
            if (
                physical_position is not None
                and physical_position.upper() in NON_AIR_POSITIONS
                and role.in_chamber_air_aggregate is True
            ):
                raise SourceRefusal(
                    "HOT_SIDE_IN_CHAMBER_AIR",
                    f"row {line_index}: slot {slot} is hot side at row level but "
                    "the sensor block marks it chamber air",
                )
        probes.append(
            ProbeReading(
                slot=slot,
                value_c=value,
                status=_optional_text(raw.get(f"{slot}_status")),
                role=probe_role,
                age_ms=_optional_int(
                    raw.get(f"{slot}_age_ms"),
                    field=f"{slot}_age_ms",
                    context=f"row {line_index}",
                ),
                rom=rom.upper() if rom is not None else None,
                physical_position=(
                    physical_position.upper() if physical_position is not None else None
                ),
            )
        )
    door_raw = _optional_text(raw.get("door_open"))
    if door_raw not in (None, "0", "1", "UNKNOWN"):
        raise SourceRefusal(
            "DOOR_VOCABULARY_VIOLATION",
            f"row {line_index}: door_open={door_raw!r} is not 0, 1 or UNKNOWN; "
            "raw levels have no domain meaning without the documented vocabulary",
        )
    door_polarity = _optional_text(raw.get("door_polarity"))
    if door_polarity not in (None, "CONFIRMED", "UNCONFIRMED"):
        raise SourceRefusal(
            "DOOR_VOCABULARY_VIOLATION",
            f"row {line_index}: door_polarity={door_polarity!r} is not "
            "CONFIRMED/UNCONFIRMED",
        )
    door_state = _normalize_door_state(door_raw, door_polarity)
    voltage = _optional_float(raw.get("voltage_v"), field="voltage_v", context=f"row {line_index}")
    current = _optional_float(raw.get("current_a"), field="current_a", context=f"row {line_index}")
    power = _optional_float(raw.get("power_w"), field="power_w", context=f"row {line_index}")
    energy = _optional_float(raw.get("energy_wh"), field="energy_wh", context=f"row {line_index}")
    measured_fields = tuple(
        name
        for name, value in (
            ("voltage_v", voltage),
            ("current_a", current),
            ("power_w", power),
            ("energy_wh", energy),
        )
        if value is not None
    )
    applied_permille = _optional_int(
        raw.get("pwm_applied_permille"),
        field="pwm_applied_permille",
        context=f"row {line_index}",
    )
    requested_permille = _optional_int(
        raw.get("pwm_req_permille"),
        field="pwm_req_permille",
        context=f"row {line_index}",
    )
    readback_permille = _optional_int(
        raw.get("pwm_readback_permille"),
        field="pwm_readback_permille",
        context=f"row {line_index}",
    )
    for name, value in (
        ("pwm_applied_permille", applied_permille),
        ("pwm_req_permille", requested_permille),
        ("pwm_readback_permille", readback_permille),
    ):
        if value is not None and not 0 <= value <= 1000:
            raise SourceRefusal(
                "ACTUATION_RANGE_VIOLATION",
                f"row {line_index}: {name}={value} is outside [0, 1000] permille",
            )
    device_state = _optional_text(raw.get("state"))
    applied_cooling = _applied_cooling_state(device_state, applied_permille)
    applied_duty = (
        applied_permille / 1000.0 if applied_permille is not None else None
    )
    quality = _row_quality(raw, line_index)
    overall_quality = _optional_text(raw.get("quality"))
    if overall_quality is not None and overall_quality not in QUALITY_VALUES:
        raise SourceRefusal(
            "QUALITY_VOCABULARY_VIOLATION",
            f"row {line_index}: overall quality {overall_quality!r} is not in "
            f"{QUALITY_VALUES}",
        )
    producer_quality = _optional_text(raw.get("producer_quality"))
    if producer_quality is not None and producer_quality not in QUALITY_VALUES:
        raise SourceRefusal(
            "QUALITY_VOCABULARY_VIOLATION",
            f"row {line_index}: producer quality {producer_quality!r} is not in "
            f"{QUALITY_VALUES}",
        )
    usable_for = _pipe_list(raw.get("usable_for"))
    invalid_reasons = _pipe_list(raw.get("invalidation_reasons"))
    dedup_key = _pipe_list(raw.get("dedup_key"))
    source_line = _optional_int(
        raw.get("source_line_index"),
        field="source_line_index",
        context=f"row {line_index}",
    )
    return NormalizedRow(
        seq=seq,
        boot_id=boot_id,
        run_id=row_run_id,
        device_id=row_device_id,
        hardware_config_id=row_hardware_id,
        firmware_version=row_firmware,
        device_ms=device_ms,
        event_time_utc=event_time,
        host_capture_time_utc=host_time,
        probes=tuple(probes),
        t_air_c=_optional_float(raw.get("air_c"), field="air_c", context=f"row {line_index}"),
        rh_pct=_optional_float(raw.get("rh_pct"), field="rh_pct", context=f"row {line_index}"),
        pressure_hpa=_optional_float(
            raw.get("pressure_hpa"), field="pressure_hpa", context=f"row {line_index}"
        ),
        door_state=door_state,
        door_polarity=door_polarity,
        cooling_voltage_v=voltage,
        cooling_current_a=current,
        cooling_power_w=power,
        cooling_energy_counter_wh=energy,
        electrical_measured_fields=measured_fields,
        applied_cooling=applied_cooling,
        applied_duty=applied_duty,
        applied_duty_permille=applied_permille,
        requested_duty_permille=requested_permille,
        readback_duty_permille=readback_permille,
        device_state=device_state,
        experiment_phase=_optional_text(raw.get("experiment_phase")),
        quality=quality,
        overall_quality=overall_quality,
        producer_quality=producer_quality,
        usable_for=usable_for,
        invalidation_reasons=invalid_reasons,
        source_line_index=source_line,
        dedup_key=dedup_key,
    )


def _row_quality(raw: Mapping[str, Any], line_index: int) -> tuple[tuple[str, str], ...]:
    quality: list[tuple[str, str]] = []
    domain_columns = {
        "producer": "producer_quality",
        "thermal": "thermal_quality",
        "environment": "environment_quality",
        "electrical": "electrical_quality",
        "door": "door_quality",
        "sequence": "sequence_quality",
        "provenance": "provenance_quality",
        "overall": "quality",
    }
    for domain, column in domain_columns.items():
        value = _optional_text(raw.get(column))
        if value is None:
            continue
        if value not in QUALITY_VALUES:
            raise SourceRefusal(
                "QUALITY_VOCABULARY_VIOLATION",
                f"row {line_index}: {domain}_quality={value!r} is not in "
                f"{QUALITY_VALUES}",
            )
        quality.append((domain, value))
    return tuple(quality)


def _a_time_semantics(
    payload: Mapping[str, Any], rows: tuple[NormalizedRow, ...], path: Path
) -> TimeSemantics:
    semantics = payload.get("timestamp_semantics")
    if not isinstance(semantics, dict):
        raise SourceRefusal(
            "A_EXPORT_INVALID",
            f"{_display_path(path)}: timestamp_semantics must be a mapping",
        )
    status = semantics.get("timestamp_utc_status")
    source = semantics.get("timestamp_utc_source")
    any_event_time = any(row.event_time_utc is not None for row in rows)
    if status == "UNAVAILABLE":
        if any_event_time:
            raise SourceRefusal(
                "TIME_SEMANTICS_CONTRADICTION",
                f"{_display_path(path)}: rows carry event UTC while "
                "timestamp_utc_status says UNAVAILABLE",
            )
        if source != "DEVICE_HAS_NO_WALL_CLOCK":
            raise SourceRefusal(
                "TIME_SEMANTICS_UNDECLARED",
                f"{_display_path(path)}: unavailable device time must state "
                "timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK",
            )
        return TimeSemantics(
            domain=TIME_BOOT_SCOPED_UPTIME,
            event_time_status="UNAVAILABLE",
            clock_sync="NOT_EVIDENCED",
            boot_scoped=True,
            cross_boot_join_allowed=False,
            absolute_latency_supported=False,
            detail=(
                "device has no wall clock; device_ms is uptime since boot_id, "
                "host capture time is a separate domain"
            ),
        )
    if status in ("AVAILABLE", "SYNCED"):
        if not any_event_time:
            raise SourceRefusal(
                "TIME_SEMANTICS_CONTRADICTION",
                f"{_display_path(path)}: timestamp_utc_status={status!r} but no "
                "row carries an event UTC timestamp",
            )
        synced = status == "SYNCED" or semantics.get("clock_sync") == "EVIDENCED"
        return TimeSemantics(
            domain=TIME_EVENT_UTC,
            event_time_status="AVAILABLE",
            clock_sync="EVIDENCED" if synced else "UNVERIFIED_SYNC",
            boot_scoped=True,
            cross_boot_join_allowed=synced,
            absolute_latency_supported=synced,
            detail=(
                "device event time is present; clock synchronisation evidence "
                "is required before cross-boot or absolute-latency claims"
            ),
        )
    raise SourceRefusal(
        "TIME_SEMANTICS_UNDECLARED",
        f"{_display_path(path)}: unsupported timestamp_utc_status {status!r}",
    )


def _a_validity_from_export(payload: Mapping[str, Any]) -> AValidityEvidence:
    invalidation = payload.get("invalidation")
    if not isinstance(invalidation, dict):
        raise SourceRefusal(
            "A_VALIDITY_SUMMARY_MISSING",
            "A export must carry an invalidation summary",
        )
    summary = invalidation.get("summary")
    if not isinstance(summary, dict):
        raise SourceRefusal(
            "A_VALIDITY_SUMMARY_MISSING",
            "A export invalidation.summary must be a mapping",
        )
    return AValidityEvidence(
        source="a-w09-export-summary",
        is_valid=None,
        status="EXPORT_SUMMARY_ONLY",
        reasons=tuple(
            f"{code}: {count}"
            for code, count in sorted(
                (summary.get("reason_counts") or {}).items()
            )
        ),
        rows_usable_per_scenario=_int_mapping(
            summary.get("rows_usable_per_scenario")
        ),
        required_domains=_domain_mapping(summary.get("scenario_required_domains")),
        reason_counts=_int_mapping(summary.get("reason_counts")),
        rows_total=(
            summary.get("rows_total")
            if isinstance(summary.get("rows_total"), int)
            else None
        ),
        usable_fraction=(
            float(summary["usable_fraction"])
            if isinstance(summary.get("usable_fraction"), (int, float))
            else None
        ),
        hardware_config_verified=_optional_bool(payload.get("hardware_config_verified")),
        calibration_verified=_optional_bool(payload.get("calibration_verified")),
        clock_sync_verified=_optional_bool(payload.get("clock_sync_verified")),
        valid_scenarios=(),
    )


def load_a_run_index(source: str | Path) -> dict[str, Any]:
    """Load A's W09 run index (the authoritative hand-off surface)."""
    path = _require_source_path(source)
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise SourceRefusal(
            "A_RUN_INDEX_INVALID",
            f"{_display_path(path)}: run index must be a JSON mapping",
        )
    if payload.get("index_version") != A_RUN_INDEX_VERSION:
        raise SourceRefusal(
            "A_RUN_INDEX_VERSION_UNSUPPORTED",
            f"{_display_path(path)}: index_version "
            f"{payload.get('index_version')!r} is not {A_RUN_INDEX_VERSION!r}",
        )
    required = {"runs", "valid_s1_run_ids_for_member_b", "blocked_run_ids"}
    missing = sorted(required - set(payload))
    if missing:
        raise SourceRefusal(
            "A_RUN_INDEX_INVALID",
            f"{_display_path(path)}: missing fields {missing}",
        )
    valid_ids_raw = payload.get("valid_s1_run_ids_for_member_b")
    if not isinstance(valid_ids_raw, list):
        raise SourceRefusal(
            "A_RUN_INDEX_INVALID",
            f"{_display_path(path)}: valid_s1_run_ids_for_member_b must be a "
            "list of run-id strings",
        )
    for index, valid_id in enumerate(valid_ids_raw):
        if not isinstance(valid_id, str) or not valid_id.strip():
            raise SourceRefusal(
                "A_RUN_INDEX_INVALID",
                f"{_display_path(path)}: valid_s1_run_ids_for_member_b[{index}] "
                "is not a non-empty string",
            )
    for section in ("runs", "blocked_run_ids"):
        entries = payload.get(section)
        if not isinstance(entries, list):
            raise SourceRefusal(
                "A_RUN_INDEX_INVALID",
                f"{_display_path(path)}: {section} must be a list",
            )
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise SourceRefusal(
                    "A_RUN_INDEX_INVALID",
                    f"{_display_path(path)}: {section}[{index}] is not a mapping",
                )
            if not any(
                entry.get(key) not in (None, "")
                for key in ("run_id", "boot_id", "device_run_label")
            ):
                raise SourceRefusal(
                    "A_RUN_INDEX_INVALID",
                    f"{_display_path(path)}: {section}[{index}] carries no "
                    "run_id, boot_id or device_run_label; an anonymous ledger "
                    "entry cannot be matched and is not trusted",
                )
    return payload


def _entry_identity_match(
    entry: Mapping[str, Any],
    *,
    run_id: Any,
    boot_id: Any,
    label: Any,
) -> bool:
    """Strict match for a *runs* entry: all comparable identities agree."""
    entry_run = entry.get("run_id")
    entry_boot = entry.get("boot_id")
    entry_label = entry.get("device_run_label")
    checks: list[bool] = []
    if entry_run is not None and run_id is not None:
        if str(entry_run) != str(run_id):
            return False
        checks.append(True)
    if entry_boot is not None and boot_id is not None:
        if str(entry_boot) != str(boot_id):
            return False
        checks.append(True)
    if entry_label is not None and label is not None:
        if str(entry_label) != str(label):
            return False
        checks.append(True)
    return bool(checks)


def _blocked_entry_match(
    blocked: Mapping[str, Any],
    *,
    run_id: Any,
    boot_id: Any,
    label: Any,
) -> tuple[bool, tuple[str, ...]]:
    """Match a blocked-ledger entry; any strong identity match blocks.

    The blocked ledger is authoritative, so a matching run_id or boot_id is
    enough to exclude the run even when another field disagrees (the
    disagreement is reported as a ledger contradiction). A label-only match is
    used only when no strong identity is comparable.
    """
    comparable = [
        (key, blocked.get(key), primary)
        for key, primary in (
            ("run_id", run_id),
            ("boot_id", boot_id),
            ("device_run_label", label),
        )
        if blocked.get(key) not in (None, "") and primary not in (None, "")
    ]
    if not comparable:
        return False, ()
    strong = [item for item in comparable if item[0] in ("run_id", "boot_id")]
    strong_matches = [key for key, value, primary in strong if str(value) == str(primary)]
    contradictions = tuple(
        key for key, value, primary in comparable if str(value) != str(primary)
    )
    if strong_matches:
        return True, contradictions
    if strong:
        return False, ()
    label_matches = [
        key
        for key, value, primary in comparable
        if key == "device_run_label" and str(value) == str(primary)
    ]
    if label_matches:
        return True, contradictions
    return False, ()


def _scenario_tokens(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    tokens: set[str] = set()
    for item in value:
        text = str(item).strip().upper()
        match = re.match(r"^(S[1-6])", text)
        tokens.add(match.group(1) if match else text)
    return tuple(sorted(tokens))


def _select_a_index_entry(
    index: Mapping[str, Any], run: RunIdentity, export_path: Path
) -> dict[str, Any]:
    run_id = run.run_id
    boot_id = run.boot_id
    label = run.device_run_label
    candidates = [
        entry
        for entry in index.get("runs", [])
        if isinstance(entry, dict)
        and _entry_identity_match(
            entry, run_id=run_id, boot_id=boot_id, label=label
        )
    ]
    if len(candidates) > 1:
        raise SourceRefusal(
            "A_RUN_INDEX_AMBIGUOUS",
            f"{_display_path(export_path)}: {len(candidates)} run-index entries "
            "match the export boot/label pair",
        )
    if not candidates:
        raise SourceRefusal(
            "A_RUN_INDEX_ENTRY_MISSING",
            f"{_display_path(export_path)}: no run-index entry matches "
            f"boot_id={boot_id!r} device_run_label={label!r}; missing evidence "
            "is not treated as valid",
        )
    return candidates[0]


def _a_validity_from_index(
    index: Mapping[str, Any],
    entry: Mapping[str, Any],
    *,
    run: RunIdentity,
    source: str,
) -> AValidityEvidence:
    valid_ids = {
        str(run_id)
        for run_id in index.get("valid_s1_run_ids_for_member_b", [])
        if str(run_id).strip()
    }
    primary_run_id = run.run_id if run.run_id is not None else entry.get("run_id")
    primary_boot_id = run.boot_id if run.boot_id is not None else entry.get("boot_id")
    primary_label = (
        run.device_run_label
        if run.device_run_label is not None
        else entry.get("device_run_label")
    )
    blocked_matches: list[tuple[Mapping[str, Any], tuple[str, ...]]] = []
    for blocked in index.get("blocked_run_ids", []):
        if not isinstance(blocked, dict):
            continue
        matched, contradictions = _blocked_entry_match(
            blocked,
            run_id=primary_run_id,
            boot_id=primary_boot_id,
            label=primary_label,
        )
        if matched:
            blocked_matches.append((blocked, contradictions))
    run_id = entry.get("run_id")
    explicit_valid = _optional_bool(entry.get("is_valid"))
    explicit_scenarios = _scenario_tokens(
        entry.get("valid_for_scenarios", entry.get("valid_scenarios"))
    )
    if blocked_matches:
        # A blocked-ledger entry is authoritative even when the same id also
        # appears in the valid list or an explicit is_valid=true claim.
        is_valid = False
        status = "INVALID"
        valid_scenarios: tuple[str, ...] = ()
        reasons_list = [
            str(reason)
            for blocked, _contradictions in blocked_matches
            for reason in blocked.get("reasons", [])
        ]
        for _blocked, contradictions in blocked_matches:
            if contradictions:
                reasons_list.append(
                    "LEDGER_IDENTITY_CONTRADICTION: blocked entry disagrees on "
                    f"{list(contradictions)}; the blocked ledger still wins"
                )
        if (
            (run_id is not None and str(run_id) in valid_ids)
            or explicit_valid is True
        ):
            reasons_list.insert(
                0,
                "CONTRADICTORY_LEDGER: run is listed as valid and blocked; "
                "the blocked ledger wins",
            )
        reasons = tuple(reasons_list)
    elif explicit_valid is True:
        is_valid = True
        status = "VALID"
        valid_scenarios = explicit_scenarios
        reasons = (
            "run index explicitly marks the run valid"
            + (
                f" for scenarios {list(explicit_scenarios)}"
                if explicit_scenarios
                else " without a scenario scope"
            ),
        )
    elif explicit_valid is False:
        is_valid = False
        status = "INVALID"
        valid_scenarios = ()
        reasons = tuple(
            str(reason) for reason in entry.get("reasons", [])
        ) or ("run index explicitly marks the run invalid",)
    elif run_id is not None and str(run_id) in valid_ids:
        is_valid = True
        status = "VALID_FOR_S1"
        valid_scenarios = ("S1",)
        reasons = (
            "run is listed in valid_s1_run_ids_for_member_b (S1-scoped)",
        )
    else:
        is_valid = None
        status = "UNKNOWN"
        valid_scenarios = ()
        reasons = (
            "run is neither in the valid list nor in the blocked ledger; "
            "unknown is not upgraded to valid",
        )
    if run.run_id is None and is_valid is True:
        # A validity grant cannot be bound to a capture whose own run identity
        # is unresolved; keep the evidence object honest for downstream users.
        is_valid = None
        status = "UNKNOWN"
        valid_scenarios = ()
        reasons = (
            "capture run identity is unresolved; A validity cannot be bound "
            "to this capture",
            *reasons,
        )
    usable_fraction = entry.get("usable_fraction")
    return AValidityEvidence(
        source=f"a-run-index:{source}",
        is_valid=is_valid,
        status=status,
        reasons=reasons,
        rows_usable_per_scenario=_int_mapping(entry.get("frames_usable_per_scenario")),
        required_domains=_domain_mapping(entry.get("scenario_required_domains")),
        reason_counts=_int_mapping(entry.get("top_invalidation_reasons")),
        rows_total=(
            entry.get("frames_total")
            if isinstance(entry.get("frames_total"), int)
            else None
        ),
        usable_fraction=(
            float(usable_fraction)
            if isinstance(usable_fraction, (int, float))
            else None
        ),
        hardware_config_verified=_optional_bool(entry.get("hardware_config_verified")),
        calibration_verified=_optional_bool(entry.get("calibration_verified")),
        clock_sync_verified=_optional_bool(entry.get("clock_sync_verified")),
        valid_scenarios=valid_scenarios,
    )


def _pinned_sources(
    provenance: Any, export_path: Path
) -> tuple[tuple[str, str | None, bool | None], ...]:
    if not isinstance(provenance, dict):
        raise SourceRefusal(
            "A_PROVENANCE_MISSING",
            f"{_display_path(export_path)}: provenance must be a mapping",
        )
    sources = provenance.get("sources")
    if not isinstance(sources, list) or not sources:
        raise SourceRefusal(
            "A_PROVENANCE_MISSING",
            f"{_display_path(export_path)}: provenance.sources must be non-empty",
        )
    repo_root = _repo_root(export_path)
    pinned: list[tuple[str, str | None, bool | None]] = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise SourceRefusal(
                "A_PROVENANCE_INVALID",
                f"{_display_path(export_path)}: provenance.sources[{index}] is "
                "not a mapping",
            )
        rel = source.get("path")
        digest = source.get("sha256")
        if not isinstance(rel, str) or not rel.strip():
            raise SourceRefusal(
                "A_PROVENANCE_INVALID",
                f"{_display_path(export_path)}: provenance.sources[{index}].path "
                "is required",
            )
        if not isinstance(digest, str) or not SHA256_PATTERN.match(digest):
            raise SourceRefusal(
                "A_PROVENANCE_UNPINNED",
                f"{_display_path(export_path)}: source {rel!r} is not SHA-256 "
                "pinned; an unpinned byte stream is not evidence-grade",
            )
        exists: bool | None = None
        if repo_root is not None:
            candidate = repo_root / rel
            if candidate.is_file():
                exists = True
                actual = _sha256_file(candidate)
                if actual != digest:
                    raise SourceRefusal(
                        "SOURCE_HASH_MISMATCH",
                        f"{_display_path(export_path)}: pinned source {rel!r} "
                        f"hashes to {actual}, not {digest}; the export's "
                        "provenance no longer matches the repository bytes",
                    )
            else:
                exists = False
        pinned.append((rel, digest, exists))
    return tuple(pinned)


# ---------------------------------------------------------------------------
# C telemetry-v1 adapter
# ---------------------------------------------------------------------------


def _looks_like_c_telemetry(payload: Mapping[str, Any]) -> bool:
    required = {
        "device_id",
        "boot_id",
        "seq",
        "captured_at",
        "thermal",
        "environment",
        "door",
        "electrical",
        "actuation",
        "quality",
    }
    return required <= set(payload)


def _load_c_telemetry(path: Path) -> Capture:
    payload = _read_json(path)
    assert isinstance(payload, dict)
    _reject_legacy_keys(payload, path)
    try:
        observation = _observation_from_c_payload(payload)
        validate_observation(observation)
    except SourceRefusal:
        raise
    except Exception as exc:  # DataContractError and validation failures
        raise SourceRefusal(
            "C_TELEMETRY_CONTRACT_VIOLATION",
            f"{_display_path(path)}: {exc}",
        ) from exc
    note = payload.get("note")
    note_text = note.lower() if isinstance(note, str) else ""
    synthetic = (
        "synthetic" in note_text
        and ("not a physical measurement" in note_text or "not physical" in note_text)
    )
    provenance = PROVENANCE_SYNTHETIC if synthetic else PROVENANCE_UNVERIFIED
    rows = (_normalized_row_from_observation(observation),)
    sensors: tuple[SensorRole, ...] = tuple(
        SensorRole(
            slot=slot,
            rom=None,
            rom_source=None,
            rom_readback_verified=None,
            physical_position=None,
            position_source=None,
            in_chamber_air_aggregate=None,
            exclusion_reason=None,
            raw_roles=(),
            role_conflict=None,
        )
        for slot in ("t1", "t2", "t3")
    )
    time = TimeSemantics(
        domain=TIME_EVENT_UTC,
        event_time_status="AVAILABLE",
        clock_sync="UNVERIFIED_SYNC",
        boot_scoped=True,
        cross_boot_join_allowed=False,
        absolute_latency_supported=False,
        detail=(
            "captured_at is timezone-aware event time; the observed v0 wire "
            "contract carries no time_sync field, so absolute-latency and "
            "cross-boot claims remain unsupported"
        ),
    )
    return Capture(
        source=SourceIdentity(
            path=_display_path(path),
            sha256=_sha256_file(path),
            format=SOURCE_FORMAT_C_TELEMETRY_V1,
            schema_namespace=SCHEMA_NAMESPACE_C,
            provenance=provenance,
            is_physical_measurement=False if synthetic else None,
            pinned_sources=(),
        ),
        run=RunIdentity(
            run_id=observation.run_id,
            run_id_status=(
                "SOURCE_CARRIED_SINGLE"
                if observation.run_id is not None
                else "NOT_CARRIED_BY_SOURCE"
            ),
            run_ids=(observation.run_id,) if observation.run_id else (),
            boot_id=observation.boot_id,
            boot_id_status="SOURCE_CARRIED_SINGLE",
            device_id=observation.device_id,
            device_id_status="CARRIED",
            hardware_config_id=observation.hardware_config_id,
            hardware_config_status="DECLARED_NOT_VERIFIED",
            firmware_version=observation.firmware_version,
            firmware_version_status="CARRIED",
            calibration_id=observation.calibration_id,
            calibration_status=(
                "DECLARED_NOT_VERIFIED"
                if observation.calibration_id is not None
                else "NOT_AVAILABLE"
            ),
            scenario_id=None,
            scenario_status="NOT_CARRIED",
            controller_id=None,
            controller_status="NOT_CARRIED",
            device_run_label=None,
        ),
        time=time,
        rows=rows,
        sensors=sensors,
        a_validity=None,
        declared_unavailable_fields=(
            "sensor_rom",
            "sensor_physical_position",
            "sensor_role",
            "scenario_id",
            "controller_id",
            "run_validity",
            "clock_sync",
        ),
        recognized_fields=tuple(sorted(payload)),
        unknown_fields=(),
        warnings=(
            (
                "synthetic fixture self-labelled; diagnostic use only, never "
                "physical evidence",
            )
            if synthetic
            else (
                "C payload provenance is unverified: no self-label or physical "
                "validity evidence; physical qualification is refused",
            )
        ),
    )


def _reject_legacy_keys(payload: Mapping[str, Any], path: Path) -> None:
    stack: list[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key.lower() in LEGACY_FORBIDDEN_KEYS:
                    raise SourceRefusal(
                        "LEGACY_FORBIDDEN_FIELD",
                        f"{_display_path(path)}: legacy field {key!r} is "
                        "forbidden; ColdGuard P0 has one cooling branch and no "
                        "INA226/second-TEC channel",
                    )
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)


_C_WIRE_EXACT_INT_PATHS = (("seq",), ("uptime_ms",))
_C_WIRE_STRING_PATHS = (
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
)
_C_WIRE_NUMERIC_PATHS = (
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


def _validate_c_wire_types(payload: Mapping[str, Any]) -> None:
    """Reject wire values that only become valid after source coercion.

    Mirrors C's strict wire gate (``strict_type_errors``) without importing
    backend runtime dependencies: exact JSON integers for counters, JSON
    strings for identity/enum fields, and finite JSON numbers (never booleans
    or numeric strings) for measurements. ``None`` stays legal where the C
    contract permits a missing channel.
    """

    def lookup(path: tuple[str, ...]) -> tuple[bool, Any]:
        node: Any = payload
        for key in path:
            if not isinstance(node, Mapping) or key not in node:
                return False, None
            node = node[key]
        return True, node

    def wire_type_error(
        path: tuple[str, ...], expected: str, value: Any
    ) -> SourceRefusal:
        return SourceRefusal(
            "C_TELEMETRY_WIRE_TYPE",
            f"C wire field {'.'.join(path)} must be {expected}, "
            f"got {type(value).__name__}",
        )

    for path in _C_WIRE_EXACT_INT_PATHS:
        present, value = lookup(path)
        if present and type(value) is not int:
            raise wire_type_error(path, "an exact JSON integer", value)
    for path in _C_WIRE_STRING_PATHS:
        present, value = lookup(path)
        if present and value is not None and type(value) is not str:
            raise wire_type_error(path, "a JSON string or null", value)
    for path in _C_WIRE_NUMERIC_PATHS:
        present, value = lookup(path)
        if not present or value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise wire_type_error(path, "a finite JSON number or null", value)
        if not math.isfinite(value):
            raise SourceRefusal(
                "FIELD_NOT_FINITE",
                f"C wire field {'.'.join(path)} must be a finite JSON number",
            )


def _observation_from_c_payload(payload: Mapping[str, Any]) -> Observation:
    version = payload.get("schema_version")
    if type(version) is not int or version != 1:
        raise SourceRefusal(
            "UNSUPPORTED_SOURCE_VERSION",
            f"C telemetry schema_version {version!r} is not the supported "
            "coldguard.telemetry/v1 integer 1",
        )
    _validate_c_wire_types(payload)

    def section(name: str) -> Mapping[str, Any]:
        value = payload.get(name)
        if not isinstance(value, dict):
            raise SourceRefusal(
                "C_TELEMETRY_STRUCTURE_INVALID",
                f"section {name!r} must be a mapping",
            )
        return value

    thermal = section("thermal")
    environment = section("environment")
    door = section("door")
    electrical = section("electrical")
    actuation = section("actuation")
    quality = section("quality")
    try:
        time = parse_event_time(payload.get("captured_at"), context="captured_at")
    except Exception as exc:
        raise SourceRefusal(
            "NAIVE_TIMESTAMP_OR_INVALID_TIME",
            f"captured_at: {exc}",
        ) from exc
    return Observation(
        device_id=_required_text(payload.get("device_id"), field="device_id", context="telemetry"),
        boot_id=_required_text(payload.get("boot_id"), field="boot_id", context="telemetry"),
        seq=_required_int(payload.get("seq"), field="seq", context="telemetry"),
        time=time,
        uptime_ms=_optional_int(payload.get("uptime_ms"), field="uptime_ms", context="telemetry"),
        run_id=_optional_text(payload.get("run_id")),
        t1_c=_optional_float(thermal.get("t1"), field="thermal.t1", context="telemetry"),
        t2_c=_optional_float(thermal.get("t2"), field="thermal.t2", context="telemetry"),
        t3_c=_optional_float(thermal.get("t3"), field="thermal.t3", context="telemetry"),
        t_air_c=_optional_float(
            environment.get("t_air"), field="environment.t_air", context="telemetry"
        ),
        rh_pct=_optional_float(
            environment.get("rh"), field="environment.rh", context="telemetry"
        ),
        door_state=_required_text(
            door.get("state"), field="door.state", context="telemetry"
        ),
        cooling_voltage_v=_optional_float(
            electrical.get("voltage_v"), field="electrical.voltage_v", context="telemetry"
        ),
        cooling_current_a=_optional_float(
            electrical.get("current_a"), field="electrical.current_a", context="telemetry"
        ),
        cooling_power_w=_optional_float(
            electrical.get("power_w"), field="electrical.power_w", context="telemetry"
        ),
        cooling_energy_counter_wh=_optional_float(
            electrical.get("energy_wh"), field="electrical.energy_wh", context="telemetry"
        ),
        applied_cooling=_required_text(
            actuation.get("cooling"), field="actuation.cooling", context="telemetry"
        ),
        applied_duty=_optional_float(
            actuation.get("duty"), field="actuation.duty", context="telemetry"
        ),
        thermal_quality=_required_text(
            quality.get("thermal"), field="quality.thermal", context="telemetry"
        ),
        environment_quality=_required_text(
            quality.get("environment"), field="quality.environment", context="telemetry"
        ),
        electrical_quality=_required_text(
            quality.get("electrical"), field="quality.electrical", context="telemetry"
        ),
        overall_quality=_required_text(
            quality.get("overall"), field="quality.overall", context="telemetry"
        ),
        device_mode=_optional_text(quality.get("device_mode")),
        schema_version=version,
        hardware_config_id=_required_text(
            payload.get("hardware_config_id"),
            field="hardware_config_id",
            context="telemetry",
        ),
        firmware_version=_required_text(
            payload.get("firmware_version"),
            field="firmware_version",
            context="telemetry",
        ),
        calibration_id=_optional_text(payload.get("calibration_id")),
    )


def _normalized_row_from_observation(observation: Observation) -> NormalizedRow:
    probes = tuple(
        ProbeReading(
            slot=slot,
            value_c=value,
            status=None,
            role=None,
            age_ms=None,
            rom=None,
            physical_position=None,
        )
        for slot, value in (
            ("t1", observation.t1_c),
            ("t2", observation.t2_c),
            ("t3", observation.t3_c),
        )
    )
    measured = tuple(
        name
        for name, value in (
            ("voltage_v", observation.cooling_voltage_v),
            ("current_a", observation.cooling_current_a),
            ("power_w", observation.cooling_power_w),
            ("energy_wh", observation.cooling_energy_counter_wh),
        )
        if value is not None
    )
    return NormalizedRow(
        seq=observation.seq,
        boot_id=observation.boot_id,
        run_id=observation.run_id,
        device_id=observation.device_id,
        hardware_config_id=observation.hardware_config_id,
        firmware_version=observation.firmware_version,
        device_ms=observation.uptime_ms,
        event_time_utc=observation.time,
        host_capture_time_utc=None,
        probes=probes,
        t_air_c=observation.t_air_c,
        rh_pct=observation.rh_pct,
        pressure_hpa=None,
        door_state=observation.door_state,
        door_polarity=None,
        cooling_voltage_v=observation.cooling_voltage_v,
        cooling_current_a=observation.cooling_current_a,
        cooling_power_w=observation.cooling_power_w,
        cooling_energy_counter_wh=observation.cooling_energy_counter_wh,
        electrical_measured_fields=measured,
        applied_cooling=observation.applied_cooling,
        applied_duty=observation.applied_duty,
        applied_duty_permille=(
            int(round(observation.applied_duty * 1000))
            if observation.applied_duty is not None
            else None
        ),
        requested_duty_permille=None,
        readback_duty_permille=None,
        device_state=observation.device_mode,
        experiment_phase=None,
        quality=(
            ("thermal", observation.thermal_quality),
            ("environment", observation.environment_quality),
            ("electrical", observation.electrical_quality),
            ("overall", observation.overall_quality),
        ),
        overall_quality=observation.overall_quality,
        producer_quality=None,
        usable_for=(),
        invalidation_reasons=(),
        source_line_index=None,
        dedup_key=observation.identity,
    )


# ---------------------------------------------------------------------------
# admission ladder
# ---------------------------------------------------------------------------


def evaluate_admission(capture: Capture) -> AdmissionResult:
    """Evaluate the fail-closed W04 admission ladder for one capture."""
    blockers: list[Blocker] = []
    stage = AdmissionStage.SOURCE_RECOGNIZED

    def block(code: str, at: AdmissionStage, detail: str) -> None:
        blockers.append(Blocker(code=code, stage=at.value, detail=detail))

    if not capture.rows:
        block("EMPTY_CAPTURE", AdmissionStage.STRUCTURALLY_VALID, "capture carries no rows")
    if (
        capture.run.boot_id is None
        or capture.run.boot_id_status != "SOURCE_CARRIED_SINGLE"
    ):
        block(
            "BOOT_ID_UNRESOLVED",
            AdmissionStage.STRUCTURALLY_VALID,
            f"boot identity status {capture.run.boot_id_status!r} is not a "
            "single source-carried boot; boot-scoped identity cannot be "
            "certified",
        )
    if capture.unknown_fields:
        block(
            "UNKNOWN_FIELDS_PRESENT",
            AdmissionStage.STRUCTURALLY_VALID,
            f"unrecognized columns {list(capture.unknown_fields)}; they are not "
            "used but the source contract drift must be reviewed",
        )
    if not blockers:
        stage = AdmissionStage.STRUCTURALLY_VALID

    if capture.time.domain == TIME_NONE:
        block(
            "TIME_DOMAIN_UNDECLARED",
            AdmissionStage.USABLE_FOR_DIAGNOSTIC_QA,
            "no explicit time domain (event UTC or boot-scoped uptime)",
        )
    if capture.time.domain == TIME_EVENT_UTC and capture.time.event_time_status != "AVAILABLE":
        block(
            "EVENT_TIME_UNAVAILABLE",
            AdmissionStage.USABLE_FOR_DIAGNOSTIC_QA,
            "event-time domain declared but no usable event timestamp",
        )
    if capture.source.provenance == PROVENANCE_UNVERIFIED:
        # A useful structural/QA view is still allowed; physical admission is
        # blocked later. The warning is explicit, never a silent pass.
        pass
    if not blockers:
        stage = AdmissionStage.USABLE_FOR_DIAGNOSTIC_QA

    scenarios = _scenario_admissions(capture)
    if capture.source.provenance != PROVENANCE_PHYSICAL:
        provenance_code = {
            PROVENANCE_SYNTHETIC: "SYNTHETIC_PROVENANCE",
            PROVENANCE_NON_PHYSICAL: "NON_PHYSICAL_PROVENANCE",
        }.get(capture.source.provenance, "PROVENANCE_UNVERIFIED")
        block(
            provenance_code,
            AdmissionStage.PHYSICALLY_QUALIFIED,
            f"source provenance is {capture.source.provenance}; only a declared "
            "physical measurement can be physically qualified",
        )
    validity = capture.a_validity
    if validity is None:
        block(
            "PHYSICAL_VALIDITY_EVIDENCE_MISSING",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            "no A run-validity verdict or run index was supplied; missing "
            "evidence is never upgraded to valid",
        )
    else:
        if validity.is_valid is None:
            block(
                (
                    "PHYSICAL_VALIDITY_EVIDENCE_MISSING"
                    if validity.source == "a-w09-export-summary"
                    else "PHYSICAL_VALIDITY_UNKNOWN"
                ),
                AdmissionStage.PHYSICALLY_QUALIFIED,
                f"A validity status {validity.status!r} is not a verdict: "
                f"{'; '.join(validity.reasons) or 'no reason recorded'}",
            )
        elif validity.is_valid is False:
            block(
                "A_LEDGER_INVALID",
                AdmissionStage.PHYSICALLY_QUALIFIED,
                "A's authoritative validity ledger excludes this run"
                + (f": {'; '.join(validity.reasons)}" if validity.reasons else ""),
            )
    if (
        capture.run.run_id is None
        or capture.run.run_id_status != "SOURCE_CARRIED_SINGLE"
    ):
        block(
            "RUN_ID_UNRESOLVED",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            f"run identity status {capture.run.run_id_status!r} is not a "
            "single source-carried run; no run_id is fabricated for a dataset "
            "join",
        )
    elif not B_RUN_ID_PATTERN.match(capture.run.run_id):
        block(
            "RUN_ID_NONCANONICAL",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            f"run_id {capture.run.run_id!r} does not match the B run identity "
            "pattern CG-S<s>-<arm>-<serial>",
        )
    if capture.run.device_id is None:
        block(
            "DEVICE_IDENTITY_UNAVAILABLE",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            f"device identity status {capture.run.device_id_status!r}; "
            "cross-device identity cannot be asserted",
        )
    if capture.run.hardware_config_id is None:
        block(
            "HARDWARE_CONFIG_MISSING",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            "no hardware configuration identity was carried",
        )
    elif validity is not None and validity.hardware_config_verified is not True:
        block(
            "HARDWARE_CONFIG_UNVERIFIED",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            f"hardware configuration {capture.run.hardware_config_id!r} is a "
            "declared label; no verification evidence was supplied",
        )
    if capture.run.calibration_id is None:
        block(
            "CALIBRATION_IDENTITY_MISSING",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            "no calibration identity exists; a calibration id is never invented",
        )
    elif validity is not None and validity.calibration_verified is not True:
        block(
            "CALIBRATION_UNVERIFIED",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            f"calibration {capture.run.calibration_id!r} is declared without "
            "verification evidence",
        )
    if capture.run.scenario_id is None:
        block(
            "SCENARIO_UNIDENTIFIED",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            "the source does not identify a canonical scenario; a run label is "
            "not a scenario certification",
        )
    if capture.unknown_role_slots:
        block(
            "SENSOR_ROLE_UNKNOWN",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            f"slots {list(capture.unknown_role_slots)} have unknown/conflicting "
            "ROM, position or chamber-air membership; role-dependent analyses "
            "are inadmissible",
        )
    missing_pins = [
        rel
        for rel, _digest, exists in capture.source.pinned_sources
        if exists is False
    ]
    if missing_pins:
        block(
            "PINNED_SOURCE_MISSING",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            f"pinned source(s) {missing_pins} are absent from the repository; "
            "a declared hash without the bytes is not evidence-grade",
        )
    unverifiable_pins = [
        rel
        for rel, _digest, exists in capture.source.pinned_sources
        if exists is None
    ]
    if unverifiable_pins:
        block(
            "PINNED_SOURCE_UNVERIFIABLE",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            f"pinned source(s) {unverifiable_pins} cannot be verified against "
            "a repository checkout; evidence-grade provenance is unconfirmed",
        )
    if capture.hot_side_slots and set(capture.hot_side_slots) & set(capture.chamber_air_slots):
        block(
            "HOT_SIDE_IN_CHAMBER_AIR",
            AdmissionStage.PHYSICALLY_QUALIFIED,
            "a hot-side slot is present in the chamber-air set",
        )
    if not blockers:
        stage = AdmissionStage.PHYSICALLY_QUALIFIED

    if stage is not AdmissionStage.PHYSICALLY_QUALIFIED:
        block(
            "PHYSICALLY_QUALIFIED_REQUIRED",
            AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET,
            "predictive admission requires the physically-qualified stage",
        )
    if capture.run.scenario_id not in ("S1", "S2"):
        block(
            "SCENARIO_NOT_PREDICTIVE",
            AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET,
            f"scenario {capture.run.scenario_id!r} is not an S1/S2 predictive "
            "scenario",
        )
    scenario = _scenario_for(capture, scenarios, capture.run.scenario_id)
    if scenario is None or not scenario.eligible:
        block(
            "SCENARIO_POPULATION_INELIGIBLE",
            AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET,
            f"scenario {capture.run.scenario_id!r} has no eligible rows under "
            "A's validity summary",
        )
    if (
        validity is not None
        and validity.is_valid is True
        and capture.run.scenario_id not in validity.valid_scenarios
    ):
        block(
            "SCENARIO_VALIDITY_NOT_GRANTED",
            AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET,
            f"A's validity evidence is scoped to "
            f"{list(validity.valid_scenarios) or 'no scenario'}, not "
            f"{capture.run.scenario_id!r}; the S1 list is never reused for S2",
        )
    time_trusted = (
        capture.time.domain == TIME_EVENT_UTC
        and capture.time.event_time_status == "AVAILABLE"
        and (
            capture.time.clock_sync == "EVIDENCED"
            or (validity is not None and validity.clock_sync_verified is True)
        )
    )
    if not time_trusted:
        block(
            "TIME_DOMAIN_INSUFFICIENT_FOR_PREDICTIVE_DATASET",
            AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET,
            f"time domain {capture.time.domain!r} / sync "
            f"{capture.time.clock_sync!r} cannot support predictive event-time "
            "labels and EWT; boot-relative data stays diagnostic-only in W04",
        )
    if not blockers:
        stage = AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET

    eligible_s1 = (
        1
        if stage is AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET
        and capture.run.scenario_id == "S1"
        and validity is not None
        and validity.is_valid is True
        and "S1" in validity.valid_scenarios
        else 0
    )
    eligible_s2 = (
        1
        if stage is AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET
        and capture.run.scenario_id == "S2"
        and validity is not None
        and validity.is_valid is True
        and "S2" in validity.valid_scenarios
        else 0
    )
    final_status = (
        AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET
        if stage is AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET
        else AdmissionStage.EXCLUDED_OR_BLOCKED
    )
    readiness = "READY" if (eligible_s1 + eligible_s2) > 0 else "NOT_READY"
    return AdmissionResult(
        status=final_status,
        highest_stage=stage,
        blockers=tuple(blockers),
        scenarios=scenarios,
        eligible_s1_runs=eligible_s1,
        eligible_s2_runs=eligible_s2,
        predictive_dataset_readiness=readiness,
        capture=capture,
    )


def _scenario_admissions(capture: Capture) -> tuple[ScenarioAdmission, ...]:
    validity = capture.a_validity
    if validity is None:
        return ()
    rows_by_scenario = validity.rows_by_scenario
    domains_by_scenario = validity.domains_by_scenario
    scenarios: list[ScenarioAdmission] = []
    for scenario_id in sorted(rows_by_scenario):
        eligible_rows = rows_by_scenario[scenario_id]
        blockers: list[Blocker] = []
        if eligible_rows <= 0:
            blockers.append(
                Blocker(
                    code="NO_ELIGIBLE_ROWS_FOR_SCENARIO",
                    stage=AdmissionStage.PHYSICALLY_QUALIFIED.value,
                    detail=(
                        f"A validity summary reports 0 usable rows for "
                        f"{scenario_id}; its reason counts are "
                        f"{dict(validity.reason_counts)}"
                    ),
                )
            )
        if scenario_id == "S2_DOOR_DISTURBANCE" and eligible_rows <= 0:
            blockers.append(
                Blocker(
                    code="MISSING_EVENT_COVERAGE",
                    stage=AdmissionStage.PHYSICALLY_QUALIFIED.value,
                    detail=(
                        "S2 requires an observed, timing-qualified door "
                        "disturbance; the source carries no such event timeline"
                    ),
                )
            )
        scenarios.append(
            ScenarioAdmission(
                scenario_id=scenario_id,
                eligible=not blockers,
                eligible_rows=max(eligible_rows, 0),
                required_domains=domains_by_scenario.get(scenario_id, ()),
                blockers=tuple(blockers),
            )
        )
    return tuple(scenarios)


def _scenario_for(
    capture: Capture,
    scenarios: Iterable[ScenarioAdmission],
    scenario_id: str | None,
) -> ScenarioAdmission | None:
    if scenario_id is None:
        return None
    full_names = {
        "S1": "S1_NORMAL_BASELINE",
        "S2": "S2_DOOR_DISTURBANCE",
        "S3": "S3_THERMAL_EFFECTIVENESS_DEGRADATION",
        "S4": "S4_ACTUATION_RESPONSE_FAULT",
    }
    wanted = full_names.get(scenario_id, scenario_id)
    for scenario in scenarios:
        if scenario.scenario_id == wanted:
            return scenario
    del capture
    return None


# ---------------------------------------------------------------------------
# role-aware aggregates and multi-capture counts
# ---------------------------------------------------------------------------


def chamber_air_mean(
    capture: Capture,
    row: NormalizedRow,
    *,
    slots: Iterable[str] | None = None,
) -> float | None:
    """Mean over explicitly role-qualified chamber-air slots.

    A supplied slot list is validated, not trusted: including the hot-side
    slot raises :class:`RoleError`. Missing values make the aggregate
    ``None``; they are never zero-filled. Unknown roles are refused, so a
    payload without role evidence cannot silently use the literal
    ``mean(T1,T2,T3)``.
    """
    selected = tuple(sorted(slots)) if slots is not None else capture.chamber_air_slots
    if not selected:
        raise RoleError(
            "no role-qualified chamber-air slots are available; a chamber-air "
            "aggregate cannot be formed from unknown roles"
        )
    values: list[float] = []
    for slot in selected:
        try:
            role = capture.sensor(slot)
        except KeyError as exc:
            raise RoleError(
                f"slot {slot!r} has no role record; refusing a role-dependent "
                "aggregate"
            ) from exc
        if role.in_chamber_air_aggregate is not True:
            raise RoleError(
                f"slot {slot!r} is not in the chamber-air aggregate"
                + (
                    f" ({role.exclusion_reason})"
                    if role.exclusion_reason
                    else ""
                )
            )
        if role.physical_position not in CHAMBER_AIR_POSITIONS:
            raise RoleError(
                f"slot {slot!r} has physical position "
                f"{role.physical_position!r}, which is not chamber air"
            )
        try:
            reading = row.probe(slot)
        except KeyError as exc:
            raise RoleError(
                f"row does not carry slot {slot!r}; aggregate is undefined"
            ) from exc
        if reading.value_c is None:
            return None
        values.append(reading.value_c)
    return sum(values) / len(values)


def _physical_source_key(capture: Capture) -> tuple[Any, ...]:
    """One boot session on one device is one physical source, not one export.

    A boot identifier can be reused across unrelated devices, so the carried
    device identity is part of the session key. When no device identity is
    carried, the boot session remains the conservative dedup key; run labels
    alone never create independent sources within a session.
    """
    run = capture.run
    if run.boot_id is not None:
        if run.device_id is not None:
            return ("session", run.device_id, run.boot_id)
        return ("session", run.boot_id)
    if run.run_id is not None:
        return ("run", run.run_id)
    pinned = tuple(sorted(capture.source.pinned_sources))
    if pinned:
        return ("pinned", pinned)
    return ("sha", capture.source.sha256)


def count_independent_runs(captures: Iterable[Capture]) -> IndependentRunCount:
    """Count unique physical sources, not repeated export views (LRK-12)."""
    groups: dict[tuple[Any, ...], list[Capture]] = {}
    detail: list[dict[str, Any]] = []
    for capture in captures:
        groups.setdefault(_physical_source_key(capture), []).append(capture)
    duplicate_views = sum(len(items) - 1 for items in groups.values())
    for key, items in sorted(groups.items(), key=lambda item: str(item[0])):
        first = items[0]
        detail.append(
            {
                "source_paths": [capture.source.path for capture in items],
                "pinned_sources": [
                    {"path": path, "sha256": digest, "exists": exists}
                    for path, digest, exists in first.source.pinned_sources
                ],
                "counted_as_independent_physical_source": True,
                "views": len(items),
                "run_id": first.run.run_id,
                "boot_id": first.run.boot_id,
                "device_id": first.run.device_id,
            }
        )
    return IndependentRunCount(
        unique_physical_sources=len(groups),
        duplicate_views=duplicate_views,
        detail=tuple(detail),
    )


_STAGE_ORDER = {
    AdmissionStage.SOURCE_RECOGNIZED: 0,
    AdmissionStage.STRUCTURALLY_VALID: 1,
    AdmissionStage.USABLE_FOR_DIAGNOSTIC_QA: 2,
    AdmissionStage.PHYSICALLY_QUALIFIED: 3,
    AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET: 4,
}


def _admission_signature(result: AdmissionResult) -> tuple[Any, ...]:
    """Comparable verdict signature for one view of a physical source."""
    return (
        result.eligible,
        result.eligible_s1_runs,
        result.eligible_s2_runs,
        tuple(sorted((blocker.code, blocker.stage) for blocker in result.blockers)),
        tuple(
            sorted(
                (scenario.scenario_id, scenario.eligible, scenario.eligible_rows)
                for scenario in result.scenarios
            )
        ),
    )


def _view_sort_key(result: AdmissionResult) -> tuple[Any, ...]:
    return (
        result.capture.source.path,
        result.capture.source.sha256,
        result.status.value,
        _STAGE_ORDER.get(result.highest_stage, -1),
        _admission_signature(result),
    )


def _summarize_physical_source(
    items: list[AdmissionResult],
) -> tuple[int, int, dict[str, Any] | None]:
    """One verdict per physical source; contradictory views fail closed."""
    ordered = sorted(items, key=_view_sort_key)
    representative = ordered[0]
    if len({_admission_signature(item) for item in ordered}) == 1:
        if representative.eligible:
            return (
                representative.eligible_s1_runs,
                representative.eligible_s2_runs,
                None,
            )
        return (
            0,
            0,
            {
                "source_path": representative.capture.source.path,
                "status": representative.status.value,
                "highest_stage": representative.highest_stage.value,
                "blockers": [
                    blocker.to_dict() for blocker in representative.blockers
                ],
                "eligible_s1_runs": 0,
                "eligible_s2_runs": 0,
                "views": len(ordered),
            },
        )

    conflict = Blocker(
        code="DUPLICATE_VIEW_ADMISSION_CONFLICT",
        stage=AdmissionStage.ELIGIBLE_FOR_PREDICTIVE_DATASET.value,
        detail=(
            "repeated views of one physical source disagree on admission or "
            "validity evidence; the source is excluded instead of keeping the "
            "most advanced view (views: "
            + "; ".join(
                f"{item.capture.source.path} status={item.status.value} "
                f"stage={item.highest_stage.value}"
                for item in ordered
            )
            + ")"
        ),
    )
    merged: dict[tuple[str, str, str], Blocker] = {}
    for item in ordered:
        for blocker in item.blockers:
            merged[(blocker.code, blocker.stage, blocker.detail)] = blocker
    conservative = min(
        ordered, key=lambda item: _STAGE_ORDER.get(item.highest_stage, -1)
    )
    return (
        0,
        0,
        {
            "source_path": representative.capture.source.path,
            "source_paths": sorted(
                {item.capture.source.path for item in ordered}
            ),
            "status": AdmissionStage.EXCLUDED_OR_BLOCKED.value,
            "highest_stage": conservative.highest_stage.value,
            "blockers": [conflict.to_dict()]
            + [merged[key].to_dict() for key in sorted(merged)],
            "eligible_s1_runs": 0,
            "eligible_s2_runs": 0,
            "views": len(ordered),
            "view_verdicts": [
                {
                    "source_path": item.capture.source.path,
                    "source_sha256": item.capture.source.sha256,
                    "status": item.status.value,
                    "highest_stage": item.highest_stage.value,
                    "eligible": item.eligible,
                    "eligible_s1_runs": item.eligible_s1_runs,
                    "eligible_s2_runs": item.eligible_s2_runs,
                    "blocker_codes": [
                        blocker.code for blocker in item.blockers
                    ],
                }
                for item in ordered
            ],
        },
    )


def summarize_readiness(results: Iterable[AdmissionResult]) -> DatasetReadiness:
    """Aggregate admission without counting repeated views as new runs.

    Identical views of one physical source collapse to one verdict.
    Contradictory eligibility/validity evidence fails closed with
    ``DUPLICATE_VIEW_ADMISSION_CONFLICT`` rather than keeping the most
    advanced or most favorable view. Output is independent of input order.
    """
    result_list = list(results)
    groups: dict[tuple[Any, ...], list[AdmissionResult]] = {}
    for result in result_list:
        groups.setdefault(_physical_source_key(result.capture), []).append(result)
    eligible_s1 = 0
    eligible_s2 = 0
    exclusions: list[dict[str, Any]] = []
    for _key, items in sorted(groups.items(), key=lambda item: str(item[0])):
        group_s1, group_s2, exclusion = _summarize_physical_source(items)
        eligible_s1 += group_s1
        eligible_s2 += group_s2
        if exclusion is not None:
            exclusions.append(exclusion)
    return DatasetReadiness(
        eligible_s1_runs=eligible_s1,
        eligible_s2_runs=eligible_s2,
        predictive_dataset_readiness=(
            "READY" if (eligible_s1 + eligible_s2) > 0 else "NOT_READY"
        ),
        unique_physical_sources=len(groups),
        duplicate_views=len(result_list) - len(groups),
        exclusions=tuple(exclusions),
    )


# ---------------------------------------------------------------------------
# small parsing helpers
# ---------------------------------------------------------------------------


def _resolve_companion(export_path: Path, relative: str) -> Path | None:
    """Resolve A's companion path without allowing parent-directory escapes."""
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        return None
    candidates = [export_path.parent / relative, export_path.parent.parent / relative]
    repo_root = _repo_root(export_path)
    if repo_root is not None:
        candidates.append(repo_root / relative)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _require_source_path(source: str | Path) -> Path:
    path = Path(source)
    if not path.is_file():
        raise SourceRefusal(
            "SOURCE_NOT_FOUND",
            f"source {path.name!r} is not a readable file",
        )
    return path


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceRefusal(
            "SOURCE_NOT_READABLE",
            f"{_display_path(path)}: {exc}",
        ) from exc


def _read_csv_header(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            return next(reader, [])
    except OSError as exc:
        raise SourceRefusal(
            "SOURCE_NOT_READABLE",
            f"{_display_path(path)}: {exc}",
        ) from exc


def _first_content_line(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip():
                    return line.strip()
    except OSError as exc:
        raise SourceRefusal(
            "SOURCE_NOT_READABLE",
            f"{_display_path(path)}: {exc}",
        ) from exc
    return ""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _repo_root(start: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _display_path(path: Path) -> str:
    """Repository-relative when possible; never a local absolute path."""
    resolved = path.resolve()
    root = _repo_root(resolved)
    if root is not None:
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            pass
    return resolved.name


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", NOT_AVAILABLE, "NONE", "None", "null"):
        return None
    return text


def _required_text(value: Any, *, field: str, context: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise SourceRefusal(
            "REQUIRED_FIELD_MISSING",
            f"{context}: {field} is required and must be a non-empty string",
        )
    return text


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _identity_text(value: Any) -> str | None:
    text = _optional_text(value)
    if text in (NOT_CARRIED_DEVICE_ID, "NOT_CARRIED_BY_SOURCE"):
        return None
    return text


def _optional_float(value: Any, *, field: str, context: str) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", NOT_AVAILABLE, "NONE", "None", "null"):
        return None
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise SourceRefusal(
            "FIELD_NOT_NUMERIC",
            f"{context}: {field}={value!r} is not numeric",
        ) from exc
    if not math.isfinite(number):
        raise SourceRefusal(
            "FIELD_NOT_FINITE",
            f"{context}: {field}={value!r} is not finite",
        )
    return number


def _optional_int(value: Any, *, field: str, context: str) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", NOT_AVAILABLE, "NONE", "None", "null"):
        return None
    try:
        number = int(text)
    except (TypeError, ValueError) as exc:
        raise SourceRefusal(
            "FIELD_NOT_INTEGER",
            f"{context}: {field}={value!r} is not an integer",
        ) from exc
    return number


def _required_int(value: Any, *, field: str, context: str) -> int:
    number = _optional_int(value, field=field, context=context)
    if number is None:
        raise SourceRefusal(
            "REQUIRED_FIELD_MISSING",
            f"{context}: {field} is required",
        )
    return number


def _pipe_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    text = str(value).strip()
    if text in ("", NOT_AVAILABLE, "NONE", "None", "null"):
        return ()
    return tuple(part for part in (item.strip() for item in text.split("|")) if part)


def _normalize_door_state(raw: str | None, polarity: str | None) -> str:
    if raw is None or raw == "UNKNOWN":
        return "UNKNOWN"
    if polarity != "CONFIRMED":
        # The raw level has no domain meaning until polarity is confirmed
        # (Doc 01 §17.7); UNKNOWN is never CLOSED.
        return "UNKNOWN"
    if raw == "0":
        return "CLOSED"
    if raw == "1":
        return "OPEN"
    return "UNKNOWN"


def _applied_cooling_state(state: str | None, applied_permille: int | None) -> str | None:
    if state == "COOLING" and applied_permille is not None and applied_permille > 0:
        return "ON"
    if state == "OFF" and applied_permille == 0:
        return "OFF"
    return None


def _int_mapping(value: Any) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, dict):
        return ()
    pairs: list[tuple[str, int]] = []
    for key, item in value.items():
        if isinstance(item, int) and not isinstance(item, bool):
            pairs.append((str(key), item))
    return tuple(sorted(pairs))


def _domain_mapping(value: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not isinstance(value, dict):
        return ()
    pairs: list[tuple[str, tuple[str, ...]]] = []
    for key, item in value.items():
        if isinstance(item, list):
            pairs.append(
                (
                    str(key),
                    tuple(str(domain) for domain in item),
                )
            )
    return tuple(sorted(pairs))


def _time_to_text(value: _dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(_dt.timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
