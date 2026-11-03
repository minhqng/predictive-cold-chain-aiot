"""ColdGuard W09 evidence-grade run export and the shared run index.

docs/05A §18 asks Week 09 to "begin evidence-grade data collection", and Member B
can only use a run if the run says what it is. This module writes that
statement: per-run exports carrying identity, sensor ROM **and** physical
position, timestamp/uptime semantics, per-field quality, experiment phase,
invalidation reasons, and provenance including the SHA-256 of every ingested
source file. The same code builds the run index that W10 and W11 exports reuse,
so a run is described once and every scenario screen reads the same description.

Non-negotiable properties, each enforced in code rather than in a comment:

* **No non-physical source can be exported.** A source whose provenance says
  ``is_physical_measurement=false`` raises. There is no override flag, because a
  flag that turns off the honesty rule is the rule's absence.
* **Excluded session classes raise.** A ``PROBE_IDENTIFICATION`` frame - the
  2026-11-02 touch-identification captures, taken with a hand on a probe - can
  never enter an S1/S2/S4 export. The rejection is by run label, so it does not
  depend on the numbers looking suspicious.
* **`timestamp_utc` stays unavailable.** The device has no wall clock
  (docs/02 §4.3: a timestamp is not dedup identity either). Where a host
  transcript prefixed its own capture time, that time is exported beside the
  device time as ``host_capture_time_utc`` with an explicit semantics label,
  never in the device field.
* **TEC_HOT_SIDE is never averaged into chamber air.** The operator-frozen
  as-built geometry puts T2 on the TEC hot side. docs/01 §20.1 literally defines
  ``Tmean = mean(T1,T2,T3)``, which on this rig mixes a heatsink temperature into
  a chamber-air state; that naming discrepancy is an open project issue and is
  exported as such, with the literal value reported *and* labelled contaminated
  rather than being silently redefined.
* **ROM ids are by-source.** No shipped frame carries a ROM id; identity comes
  from the per-boot ``#CG ROM`` lines and the frozen firmware ROM table, and the
  export says ``rom_source`` accordingly instead of implying a readback.
"""

from __future__ import annotations

import dataclasses
import datetime
import pathlib
import statistics

import cg_w09_capture_parser as capture_parser
import cg_w09_validity as validity
from cg_w09_capture_parser import PROBE_SLOTS, Frame

EXPORT_VERSION = "w09-run-export-v2"
RUN_INDEX_VERSION = "w09-run-index-v1"

RUN_ID_SINGLE = "SOURCE_CARRIED_SINGLE"
RUN_ID_AMBIGUOUS = "UNRESOLVED_MULTIPLE_SOURCE_RUN_IDS_IN_ONE_BOOT_ID"
RUN_ID_ABSENT = "NOT_CARRIED_BY_SOURCE"
BOOT_ID_SINGLE = "SOURCE_CARRIED_SINGLE"
BOOT_ID_AMBIGUOUS = "UNRESOLVED_MULTIPLE_BOOT_IDS_IN_ONE_EXPORT"
BOOT_ID_ABSENT = "NOT_CARRIED_BY_SOURCE"

# Fields every run export must carry. A missing one is an error, not a null:
# B must be able to join on identity without discovering mid-analysis that the
# campaign was never stated anywhere.
REQUIRED_EXPORT_FIELDS = (
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
REQUIRED_SENSOR_FIELDS = (
    "raw_slot",
    "rom",
    "rom_source",
    "physical_position",
    "position_source",
    "raw_role_in_capture",
    "in_chamber_air_mean",
)

# --- the per-row contract ----------------------------------------------------
#
# The dossier's own pass criterion says *every exported row* carries run_id,
# boot_id, hardware_config_id, firmware_version, sensor ROM, physical position,
# timestamp/uptime semantics, measurement-quality state, experiment phase,
# invalidation reason and source provenance. A claim about rows is only true if
# it is checkable about rows, so the list lives here, beside the code that writes
# them, and the companion CSV is rendered **from** it: the delivered header, the
# declared column set and the cells all come from one place. That is what was
# missing when the export declared 50 columns per row while the companion file
# carried 24 and none of the three names the docs quoted existed.
PROBE_ROW_SUFFIXES = ("", "_status", "_role", "_age_ms", "_rom", "_physical_position")

ROW_CONTRACT_FIELDS = (
    # identity
    "seq", "run_id", "boot_id", "device_id", "hardware_config_id", "firmware_version",
    # time: uptime is the measurement axis; UTC is stated as a gap, never invented
    "device_ms", "timestamp_utc", "timestamp_utc_status", "host_capture_time_utc",
    # provenance: which bytes this row came from
    "source_path", "source_kind", "source_line_index", "dedup_key",
    # verdict
    "experiment_phase", "quality", "usable_for", "invalidation_reasons",
    # control / state
    "stage", "state", "stop_reason", "snapshot",
    "pwm_req_permille", "pwm_applied_permille", "pwm_readback_permille",
    "door_open", "door_polarity",
    # environment and electrical, kept in the row so a reader never has to join
    "air_c", "rh_pct", "pressure_hpa", "voltage_v", "current_a", "power_w", "energy_wh",
)

# The per-row contract names fields that no shipped encoding can carry per row.
# They are stated per field with the reason instead of being silently dropped,
# because an absent field and an unsatisfied field are different claims
# (docs/01 §19.4).
ROW_CONTRACT_NOT_AVAILABLE = {
    "timestamp_utc": (
        "NOT AVAILABLE (DEVICE_HAS_NO_WALL_CLOCK); the column is delivered and empty, and "
        "timestamp_utc_status states the reason on the row"
    ),
    "host_capture_time_utc": (
        "NOT AVAILABLE where the source is a derived table rather than a host transcript; the "
        "committed W04 CSV carries no host capture time, so the column is delivered empty"
    ),
    "device_id": (
        "NOT AVAILABLE (NOT_CARRIED_BY_THIS_ENCODING); the literal token is delivered per row so "
        "the dedup key cannot be mistaken for a cross-device join"
    ),
    "calibration_id": (
        "NOT AVAILABLE PER ROW (docs/05B §6 lists it as mandatory; no shipped H8S or CSV encoding "
        "carries a calibration id, so W09 states the gap instead of publishing a column of nulls)"
    ),
    "schema_version": (
        "NOT AVAILABLE PER ROW (the derived table carries no per-row schema token; the run-level "
        "schema_version is the only place it could appear and it is null for this encoding)"
    ),
}


def _domain_quality_columns() -> tuple[str, ...]:
    return tuple(f"{domain}_quality" for domain in validity.DOMAINS)


def _probe_row_columns() -> tuple[str, ...]:
    return tuple(
        f"{slot}{suffix}"
        for slot in PROBE_SLOTS
        for suffix in PROBE_ROW_SUFFIXES
    )


# The companion CSV header, and therefore the set the export may declare.
ROW_CSV_COLUMNS: tuple[str, ...] = (
    "seq", "run_id", "boot_id", "device_id", "hardware_config_id", "firmware_version",
    "device_ms", "timestamp_utc", "timestamp_utc_status", "host_capture_time_utc",
    "source_path", "source_kind", "source_line_index", "dedup_key",
    "experiment_phase", "quality", "usable_for", *_domain_quality_columns(),
    "invalidation_reasons",
    "stage", "state", "stop_reason", "snapshot",
    "pwm_req_permille", "pwm_applied_permille", "pwm_readback_permille",
    "door_open", "door_polarity",
    *_probe_row_columns(),
    "air_c", "rh_pct", "pressure_hpa", "voltage_v", "current_a", "power_w", "energy_wh",
)

# Every name the row contract demands of a **row dict**. The companion CSV
# renders it, `_assert_complete` checks it, and `validate_w09.py` compares the
# published header against `ROW_CSV_COLUMNS`, so a declaration and a delivery can
# no longer be two different lists.
ROW_CONTRACT_DELIVERED: tuple[str, ...] = (
    ROW_CONTRACT_FIELDS + _domain_quality_columns() + _probe_row_columns()
)

NOT_AVAILABLE_CELL = "NOT_AVAILABLE"


def row_contract_block() -> dict:
    """The row contract as data: what is delivered where, and what is not."""
    return {
        "declared_by": (
            "docs/05A §18 A-W09-03 (log the invalidation, never delete the attempt) and the W09 "
            "pass criterion 'every exported row carries ...'"
        ),
        "companion_csv_columns": list(ROW_CSV_COLUMNS),
        "delivered_per_row": {
            "identity": ["seq", "run_id", "boot_id", "device_id",
                         "hardware_config_id", "firmware_version"],
            "time": ["device_ms", "timestamp_utc", "timestamp_utc_status",
                     "host_capture_time_utc"],
            "provenance": ["source_path", "source_kind", "source_line_index", "dedup_key"],
            "measurement_quality_state": list(_domain_quality_columns()),
            "invalidation_reason": ["invalidation_reasons"],
            "experiment_phase": ["experiment_phase"],
            "sensor_rom_and_physical_position": [
                f"{slot}{suffix}"
                for slot in PROBE_SLOTS
                for suffix in ("_rom", "_physical_position")
            ],
        },
        "not_available_per_row": dict(sorted(ROW_CONTRACT_NOT_AVAILABLE.items())),
        "verified_by": (
            "cg_w09_export._assert_complete() checks every row against this contract, and "
            "validate_w09.py compares the published companion header against companion_csv_columns"
        ),
    }


def _row_cell(row: dict, column: str) -> str:
    """One row's value for one companion-CSV column, stated or refused.

    Refusing here is the point: a column the row cannot answer is an export bug,
    not an empty cell a reader has to interpret.
    """
    if column.endswith("_quality") and column[: -len("_quality")] in validity.DOMAINS:
        domain = column[: -len("_quality")]
        by_domain = row.get("quality_by_domain")
        if not isinstance(by_domain, dict) or domain not in by_domain:
            raise ExportError(
                f"row {row.get('seq')!r} cannot answer the {column} column of the row contract"
            )
        return str(by_domain[domain])
    if column not in row:
        raise ExportError(
            f"row {row.get('seq')!r} is missing {column!r}, which the companion CSV declares"
        )
    value = row[column]
    if value is None:
        # An empty cell reads as "no value", which is a different claim from
        # "this field does not exist in this encoding"; the contract names the
        # gap either way, so the cell says NOT_AVAILABLE rather than nothing.
        return NOT_AVAILABLE_CELL
    if isinstance(value, (list, tuple)):
        if not value:
            # NONE is a stated empty set; NOT_AVAILABLE is "this encoding does not
            # carry the field". Collapsing them would lose the distinction.
            return "NONE"
        return "|".join(str(part) for part in value)
    return str(value)


def render_companion_csv(rows: list[dict]) -> str:
    """Render the per-row companion from the declared columns - one source.

    The cells are joined with commas and are never quoted, so a value that would
    need quoting raises instead of silently producing a file whose columns no
    reader can count. Nothing in the contract vocabulary contains a comma today.
    """
    cells = [_row_cell(row, column) for row in rows for column in ROW_CSV_COLUMNS]
    for cell in cells:
        if any(bad in cell for bad in (",", '"', "\n", "\r")):
            raise ExportError(
                f"companion-CSV cell {cell!r} needs escaping; the flat contract rendering does "
                "not quote, so the column set must not grow into something that needs it"
            )
    header = ",".join(ROW_CSV_COLUMNS)
    lines = [header] + [
        ",".join(_row_cell(row, column) for column in ROW_CSV_COLUMNS) for row in rows
    ]
    return "\n".join(lines) + "\n"


# OPERATOR-FROZEN as-built geometry. Do not re-derive, do not re-test, do not
# question: the 2026-11-02 PROBE_IDENTIFICATION session was accepted by the
# operator as the official sensor-location record.
FROZEN_GEOMETRY_VERSION = "as-built-2026-11-02-frozen"
FROZEN_SENSOR_GEOMETRY = {
    "t1": {"rom": "287088CA00000051", "position": "CHAMBER_CENTER"},
    "t2": {"rom": "28AEBF2200000006", "position": "TEC_HOT_SIDE"},
    "t3": {"rom": "28CBE9CA00000072", "position": "CHAMBER_BOTTOM"},
    "t4": {"rom": "283BE5C9000000A9", "position": "CHAMBER_NEAR_DOOR"},
}
CHAMBER_AIR_SLOTS = ("t1", "t3", "t4")   # everything except the hot side
EXCLUDED_FROM_CHAMBER_MEAN = {"t2": "TEC_HOT_SIDE is a heatsink, not chamber air"}

POSITION_SOURCE = (
    "OPERATOR_FROZEN_AS_BUILT_2026-11-02_PROBE_IDENTIFICATION_RECORD_"
    "NOT_REMEASURED_BY_W09"
)
ROM_SOURCE_BY_SOURCE = "BY_SOURCE_FROM_FIRMWARE_ROM_MAP_NO_READBACK_VERIFIED"

PHASE_PRE_FIRST_SNAPSHOT = "PRE_FIRST_SNAPSHOT"
PHASE_OFF_IDLE = "OFF_IDLE"
PHASE_ACTIVE_COOLING = "ACTIVE_COOLING"
PHASE_COOLDOWN = "COOLDOWN"
PHASE_ARMED_OTHER = "ARMED_OTHER"

TIMESTAMP_SEMANTICS = {
    "device_timestamp_utc": None,
    "timestamp_utc_status": "UNAVAILABLE",
    "timestamp_utc_source": "DEVICE_HAS_NO_WALL_CLOCK",
    "measurement_time_axis": "DEVICE_UPTIME_MS",
    "host_capture_time": "ADDED_BY_HOST_BESIDE_DEVICE_TIME_NEVER_IN_PLACE_OF_IT",
    "doc_anchor": "docs/02 §4.3, cg_telemetry_schema module contract",
}


class ExportError(RuntimeError):
    """Raised when an export would state something the evidence cannot support."""


@dataclasses.dataclass(frozen=True)
class RunSource:
    """One ingested source file for one run, pinned."""

    path: str
    sha256: str | None
    source_kind: str
    is_physical_measurement: bool
    run_label: str
    repo_tracked: bool | None = None
    note: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def repo_relative(path: str | None) -> str | None:
    """A source path as any checkout can open it, never as somebody's disk.

    ``source_path`` is a per-row provenance field now, and provenance is delivered
    957 times: an absolute path here would put a developer's machine into a pinned
    evidence artifact, which the dossier validator already refuses everywhere else
    in the week.
    """
    if path is None:
        return None
    text = str(path).replace("\\", "/")
    candidate = pathlib.PurePath(text)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return text
    return text


def utc_now_stamp() -> str:
    """Host-side generation time, labelled as host time everywhere."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_phase(frame: Frame) -> str:
    """Experiment phase from the device's own state, not from a duty guess."""
    if frame.values.get("snapshot") != "VALID":
        return PHASE_PRE_FIRST_SNAPSHOT
    state = frame.values.get("state")
    duty = frame.values.get("pwm_applied_permille")
    if state == "COOLDOWN":
        return PHASE_COOLDOWN
    if state == "COOLING" and isinstance(duty, int) and duty > 0:
        return PHASE_ACTIVE_COOLING
    if state == "OFF" and isinstance(duty, int) and duty == 0:
        return PHASE_OFF_IDLE
    return PHASE_ARMED_OTHER


def _usable_values(frames: list[Frame], field: str, usable_indexes: set[int]) -> list[float]:
    out: list[float] = []
    for index, frame in enumerate(frames):
        if index not in usable_indexes:
            continue
        value = frame.values.get(field)
        if isinstance(value, (int, float)):
            out.append(float(value))
    return out


def _status_tally(frames: list[Frame], field: str) -> dict[str, int]:
    tally: dict[str, int] = {}
    for frame in frames:
        if not frame.has(field):
            tally["ABSENT_FROM_ENCODING"] = tally.get("ABSENT_FROM_ENCODING", 0) + 1
            continue
        value = frame.values.get(field)
        key = "NONE_OR_EMPTY" if value in (None, "") else str(value)
        tally[key] = tally.get(key, 0) + 1
    return tally


def per_field_quality(frames: list[Frame]) -> dict:
    """Every field a consumer might average, with what actually qualified.

    Produced even for fields the encoding does not carry: 'absent from this
    encoding' and 'present but never OK' are different gaps and B needs both.
    """
    watched = [
        *[f"{slot}_status" for slot in PROBE_SLOTS],
        "air_c_status", "rh_pct_status", "pressure_hpa_status",
        "voltage_v_status", "current_a_status", "power_w_status",
        "door_status", "door_polarity", "door_open", "snapshot", "state", "stage",
        "stop_reason", "limits_policy", "fan", "fan_readback", "pwm_applied_permille",
    ]
    return {
        field: {
            "frames_total": len(frames),
            "status_tally": _status_tally(frames, field),
            "values_present": sum(
                1 for f in frames if isinstance(f.values.get(field.split("_status")[0]), (int, float))
                if field.endswith("_status")
            ) if field.endswith("_status") else None,
        }
        for field in watched
    }


def derived_thermal_states(frames: list[Frame], usable_indexes: set[int]) -> dict:
    """Chamber-air and hot-side statistics, kept apart on purpose.

    The literal docs/01 §20.1 mean is reported so the discrepancy is auditable,
    but it is labelled ``CONTAMINATED_ON_THIS_RIG`` and ``use_for_physics: false``:
    on this geometry its T2 term is the TEC heatsink.
    """
    stats: dict[str, dict] = {}
    for slot in PROBE_SLOTS:
        values = _usable_values(frames, slot, usable_indexes)
        position = FROZEN_SENSOR_GEOMETRY[slot]["position"]
        stats[f"{slot}_{position.lower()}"] = {
            "source_slot": slot,
            "physical_position": position,
            "definition": f"raw slot {slot} at its frozen position",
            "n": len(values),
            "mean_c": round(statistics.fmean(values), 4) if values else None,
            "min_c": round(min(values), 3) if values else None,
            "max_c": round(max(values), 3) if values else None,
            "first_c": round(values[0], 3) if values else None,
            "last_c": round(values[-1], 3) if values else None,
            "use_for_physics": True,
        }
    chamber = [
        value
        for slot in CHAMBER_AIR_SLOTS
        for value in _usable_values(frames, slot, usable_indexes)
    ]
    per_slot_means = {
        slot: statistics.fmean(_usable_values(frames, slot, usable_indexes))
        for slot in CHAMBER_AIR_SLOTS
        if _usable_values(frames, slot, usable_indexes)
    }
    stats["chamber_air_mean"] = {
        "definition": "mean of per-slot means over CHAMBER_CENTER/CHAMBER_BOTTOM/CHAMBER_NEAR_DOOR",
        "slots": list(CHAMBER_AIR_SLOTS),
        "excluded": EXCLUDED_FROM_CHAMBER_MEAN,
        "n_slots": len(per_slot_means),
        "mean_c": round(statistics.fmean(list(per_slot_means.values())), 4) if per_slot_means else None,
        "per_slot_mean_c": {k: round(v, 4) for k, v in per_slot_means.items()},
        "n_frames": len(chamber),
        "use_for_physics": True,
    }
    literal = [value for slot in ("t1", "t2", "t3") for value in _usable_values(frames, slot, usable_indexes)]
    literal_means = {
        slot: statistics.fmean(_usable_values(frames, slot, usable_indexes))
        for slot in ("t1", "t2", "t3")
        if _usable_values(frames, slot, usable_indexes)
    }
    stats["docs01_20_1_literal_tmean"] = {
        "definition": "docs/01 §20.1 literally: mean(T1,T2,T3) of raw slot names",
        "n_slots": len(literal_means),
        "mean_c": round(statistics.fmean(list(literal_means.values())), 4) if literal_means else None,
        "per_slot_mean_c": {k: round(v, 4) for k, v in literal_means.items()},
        "n_frames": len(literal),
        "use_for_physics": False,
        "quality_label": "CONTAMINATED_ON_THIS_RIG",
        "contamination_reason": (
            "the §20.1 term T2 is, on the frozen as-built geometry, TEC_HOT_SIDE; averaging it "
            "into a chamber-air state mixes a heatsink temperature into the plant variable. The "
            "slot-name-vs-position discrepancy in docs/01 §20.1 is an open project issue that "
            "W09 records rather than resolves"
        ),
    }
    hot_side = _usable_values(frames, "t2", usable_indexes)
    stats["tec_hot_side"] = {
        "definition": "raw slot t2, physical position TEC_HOT_SIDE, reported alone",
        "n": len(hot_side),
        "mean_c": round(statistics.fmean(hot_side), 4) if hot_side else None,
        "max_c": round(max(hot_side), 3) if hot_side else None,
        "use_for_physics": True,
        "never_in_chamber_mean": True,
    }
    return {
        "geometry_version": FROZEN_GEOMETRY_VERSION,
        "position_source": POSITION_SOURCE,
        "states": stats,
        "gradient_c_per_s": gradient(frames, usable_indexes),
    }


def least_squares_slope_c_per_s(series: list[tuple[int, float]]) -> float | None:
    """Ordinary least-squares slope of value on ``device_ms``, per second.

    Named because docs/01 §20.5 requires a slope to state its fit method: one
    ``dT/dt`` figure without a named estimator and a window is ambiguous, and an
    endpoint difference and a fit over the same rows are not the same number.
    """
    if len(series) < 3:
        return None
    mean_x = statistics.fmean(x for x, _ in series)
    mean_y = statistics.fmean(y for _, y in series)
    denominator = sum((x - mean_x) ** 2 for x, _ in series)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in series) / denominator * 1000.0


def gradient(frames: list[Frame], usable_indexes: set[int]) -> dict:
    """dT/dt of each chamber-air slot over the accepted rows (A-W09-04 baseline).

    docs/01 §20.5: a slope must name its temperature representation, its window
    and its fit method. Publishing one number for three possible estimators is
    how a figure that is ``(last - first) / span`` gets read as a trend, so each
    estimator is reported under its own name with the window it was computed
    over. On the committed capture the endpoint figure and the least-squares fit
    differ by roughly 3x over identical rows - the series cools and then recovers
    - and neither is a mistake: they answer different questions.
    """
    per_slot_series: dict[str, list[tuple[int, float]]] = {}
    for index, frame in enumerate(frames):
        if index not in usable_indexes:
            continue
        device_ms = frame.values.get("device_ms")
        if not isinstance(device_ms, int):
            continue
        for slot in CHAMBER_AIR_SLOTS:
            value = frame.values.get(slot)
            if isinstance(value, (int, float)):
                per_slot_series.setdefault(slot, []).append((device_ms, float(value)))
    out: dict[str, dict] = {}
    for slot, series in sorted(per_slot_series.items()):
        window = {
            "definition": (
                "every row this layer accepted for thermal use, in source order, per slot"
            ),
            "temperature_representation": (
                "the raw single-probe value of this slot; not a chamber-air mean and not Tmean"
            ),
            "first_device_ms": series[0][0] if series else None,
            "last_device_ms": series[-1][0] if series else None,
            "duration_s": (
                round((series[-1][0] - series[0][0]) / 1000.0, 3) if len(series) >= 2 else None
            ),
            "doc_anchor": "docs/01 §20.5",
        }
        deltas: list[float] = []
        for (t0, v0), (t1, v1) in zip(series, series[1:]):
            dt_s = (t1 - t0) / 1000.0
            if dt_s <= 0:
                continue
            deltas.append((v1 - v0) / dt_s)
        span_s = window["duration_s"] if len(series) >= 2 else None
        lsq = least_squares_slope_c_per_s(series)
        out[slot] = {
            "n": len(series),
            "physical_position": FROZEN_SENSOR_GEOMETRY[slot]["position"],
            "window": window,
            "least_squares_gradient_c_per_s": round(lsq, 7) if lsq is not None else None,
            "least_squares_estimator": (
                "ordinary least squares of value on device_ms over the whole window "
                "(least_squares_slope_c_per_s); uses every row, so it follows the trend the "
                "row set actually has"
            ),
            "endpoint_gradient_c_per_s": (
                round((series[-1][1] - series[0][1]) / span_s, 7)
                if span_s else None
            ),
            "endpoint_estimator": (
                "(last - first) / duration; an endpoint statistic that is blind to the path "
                "between the ends. On an evenly spaced series it equals the mean of the "
                "successive interval slopes, which is why the two agree exactly here"
            ),
            "median_successive_interval_gradient_c_per_s": (
                round(statistics.median(deltas), 7) if deltas else None
            ),
            "median_estimator": (
                "median of the per-interval slopes; the DS18B20 quantises at 0.0625 degC, so "
                "most 1 Hz intervals step by nothing and a median of 0 states that the box held "
                "frame to frame, not that it did not drift"
            ),
            "estimator_spread_c_per_s": (
                round(abs(lsq - (series[-1][1] - series[0][1]) / span_s), 7)
                if lsq is not None and span_s else None
            ),
            "reading": (
                "the two gradient figures are different estimators of different questions and "
                "are published apart; quoting either one as 'the gradient' without naming the "
                "estimator and the window repeats the ambiguity docs/01 §20.5 forbids"
            ),
        }
    return out



def sensors_block(frames: list[Frame], boot_identity: dict | None) -> list[dict]:
    """ROM **and** physical position per probe, with the source of each."""
    boot_identity = boot_identity or {}
    roms = boot_identity.get("roms", {})
    slot_by_role = {"T1": "t1", "T2": "t2", "T3": "t3", "SPARE": "t4"}
    out: list[dict] = []
    for slot in PROBE_SLOTS:
        frozen = FROZEN_SENSOR_GEOMETRY[slot]
        role_token = slot.upper() if slot != "t4" else "SPARE"
        boot_entry = roms.get(role_token) or roms.get(slot_by_role.get(role_token, ""), {})
        observed_roles = sorted({
            str(f.values.get(f"{slot}_role"))
            for f in frames if f.has(f"{slot}_role") and f.values.get(f"{slot}_role") is not None
        })
        rom = boot_entry.get("rom") or frozen["rom"]
        rom_source = (
            "BOOT_LOG_CG_ROM_LINE" if boot_entry.get("rom") else ROM_SOURCE_BY_SOURCE
        )
        if boot_entry.get("rom") and boot_entry["rom"] != frozen["rom"]:
            raise ExportError(
                f"{slot}: the capture's #CG ROM line says {boot_entry['rom']!r} but the frozen "
                f"as-built table says {frozen['rom']!r}; refusing to export a configuration "
                "mismatch rather than picking one"
            )
        out.append({
            "raw_slot": slot,
            "rom": rom,
            "rom_source": rom_source,
            "rom_readback_verified": False,
            "physical_position": frozen["position"],
            "position_source": POSITION_SOURCE,
            "raw_role_in_capture": observed_roles,
            "role_discrepancy": (
                "the capture's slot roles are commissioning-era assignments "
                "(UNASSIGNED/HOT_SIDE); the frozen 2026-11-02 record is the position authority"
                if observed_roles and set(observed_roles) != {frozen["position"]} else "none"
            ),
            "in_chamber_air_mean": slot in CHAMBER_AIR_SLOTS,
            "exclusion_reason": EXCLUDED_FROM_CHAMBER_MEAN.get(slot, ""),
            "boot_status": boot_entry.get("status"),
            "boot_present": boot_entry.get("present"),
        })
    return out


def frame_rows(
    frames: list[Frame],
    validities: list[validity.RowValidity],
    *,
    run_identity: dict | None = None,
    probe_roms: dict[str, str] | None = None,
) -> list[dict]:
    """Per-frame rows carrying the whole row contract, not a subset of it.

    ``run_identity`` (device_id / hardware_config_id / firmware_version) and
    ``probe_roms`` are run-level facts, but the pass criterion says *every row*
    carries them, and a reader who joins this file to another capture cannot
    recover them from a header in a different file. They are repeated per row
    rather than left implicit.
    """
    run_identity = run_identity or {}
    probe_roms = probe_roms or {}
    rows: list[dict] = []
    for frame, verdict in zip(frames, validities):
        row = {
            "seq": frame.seq,
            "boot_id": frame.boot_id,
            "run_id": frame.run_id,
            "device_id": run_identity.get("device_id"),
            "hardware_config_id": run_identity.get("hardware_config_id"),
            "firmware_version": run_identity.get("firmware_version"),
            "device_ms": frame.values.get("device_ms"),
            "stage": frame.values.get("stage"),
            "state": frame.values.get("state"),
            "stop_reason": frame.values.get("stop_reason"),
            "snapshot": frame.values.get("snapshot"),
            "experiment_phase": classify_phase(frame),
            "quality": verdict.quality,
            "quality_by_domain": dict(verdict.quality_by_domain),
            "usable_for": list(verdict.usable_for),
            "invalidation_reasons": list(verdict.reason_codes),
            "pwm_req_permille": frame.values.get("pwm_req_permille"),
            "pwm_applied_permille": frame.values.get("pwm_applied_permille"),
            "pwm_readback_permille": frame.values.get("pwm_readback_permille"),
            "door_open": frame.values.get("door_open"),
            "door_polarity": frame.values.get("door_polarity"),
            "timestamp_utc": None,
            "timestamp_utc_status": "UNAVAILABLE",
            "host_capture_time_utc": frame.values.get("host_capture_time_utc"),
            "dedup_key": [str(part) for part in frame.dedup_key],
            "source_path": repo_relative(frame.provenance.source_path),
            "source_kind": frame.provenance.source_kind,
            "source_line_index": frame.provenance.line_index,
        }
        for slot in PROBE_SLOTS:
            probe = frame.probe(slot)
            row[slot] = probe["value"]
            row[f"{slot}_status"] = probe["status"]
            row[f"{slot}_role"] = probe["role"]
            row[f"{slot}_age_ms"] = probe["age_ms"]
            row[f"{slot}_rom"] = probe_roms.get(slot) or FROZEN_SENSOR_GEOMETRY[slot]["rom"]
            row[f"{slot}_physical_position"] = FROZEN_SENSOR_GEOMETRY[slot]["position"]
        for field in ("air_c", "rh_pct", "pressure_hpa", "voltage_v", "current_a",
                      "power_w", "energy_wh"):
            row[field] = frame.values.get(field)
        rows.append(row)
    return rows


def _assert_complete(export: dict) -> None:
    missing = [name for name in REQUIRED_EXPORT_FIELDS if name not in export]
    if missing:
        raise ExportError(f"run export is missing required field(s): {', '.join(missing)}")
    for sensor in export["sensors"]:
        absent = [name for name in REQUIRED_SENSOR_FIELDS if name not in sensor]
        if absent:
            raise ExportError(
                f"sensor block for {sensor.get('raw_slot')!r} missing {', '.join(absent)}"
            )
    # The row contract is checked on rows, because that is what the dossier
    # claims about them. A header-only check is how "26 columns per row" came to
    # be written above a file with 24 and three of the named columns absent.
    if set(ROW_CONTRACT_FIELDS) - set(ROW_CSV_COLUMNS):
        raise ExportError(
            f"the row contract names fields the companion does not deliver: "
            f"{sorted(set(ROW_CONTRACT_FIELDS) - set(ROW_CSV_COLUMNS))}"
        )
    undeclared = sorted(set(ROW_CONTRACT_DELIVERED) - set(ROW_CSV_COLUMNS))
    if undeclared:
        raise ExportError(
            f"the row contract is delivered by fields the companion header does not declare: "
            f"{undeclared}"
        )
    frames = export.get("frames")
    if isinstance(frames, list):
        if not frames:
            raise ExportError("run export has no frame rows to check the row contract against")
        for row in frames:
            absent = [name for name in ROW_CONTRACT_FIELDS if name not in row]
            if absent:
                raise ExportError(
                    f"row {row.get('seq')!r} is missing the contracted field(s): "
                    f"{', '.join(absent)}"
                )
            # Renders through the same function that writes the companion file, so
            # a row that cannot answer a declared column - including the per-domain
            # quality columns the row carries as one dict - fails here, not in the
            # published artifact.
            render_companion_csv([row])
    else:
        raise ExportError(
            "the row contract can only be checked on inline rows; externalise the frames "
            "only after _assert_complete has run on the inline export"
        )

    if not export["provenance"].get("sources"):
        raise ExportError("run export has no pinned provenance sources")
    for source in export["provenance"]["sources"]:
        if not source.get("sha256"):
            raise ExportError(
                f"source {source.get('path')!r} was not hash-pinned; an unpinned byte stream "
                "is not evidence-grade"
            )


def build_run_export(
    frames: list[Frame],
    *,
    run_label: str,
    scenario_candidate: str,
    status_label: str,
    boot_identity: dict | None = None,
    sources: list[RunSource] | None = None,
    cadence_hz: float = 1.0,
    extra_notes: list[str] | None = None,
    generated_at_utc: str | None = None,
) -> dict:
    """Assemble one run export and prove it is complete before returning it."""
    if not frames:
        raise ExportError(f"{run_label}: refusing to export an empty run")
    non_physical = [f for f in frames if not f.provenance.is_physical_measurement]
    if non_physical:
        raise ExportError(
            f"{run_label}: {len(non_physical)} frame(s) come from a source with "
            "is_physical_measurement=false. A host fixture is not a run; it may be used to "
            "prove tooling, never to populate a dataset."
        )
    excluded = [
        f for f in frames
        if any(reason.code.startswith("EXCLUDED_SESSION_CLASS_")
               for reason in validity.excluded_session_reasons(f))
    ]
    if excluded:
        raise ExportError(
            f"{run_label}: {len(excluded)} frame(s) belong to an excluded session class "
            "and may not enter S1/S2/S4"
        )

    validities = validity.evaluate_frames(frames)
    scenario_key = scenario_candidate if scenario_candidate in validity.SCENARIO_REQUIRED_DOMAINS \
        else "S1_NORMAL_BASELINE"
    usable = {i for i, v in enumerate(validities) if scenario_key in v.usable_for}
    # Statistics that mix probe values are computed over rows that are good for
    # *thermal* reasons specifically, so an unqualified PZEM column can never
    # silently reduce a thermal baseline, and a stale probe can never silently
    # reduce an electrical one.
    thermal_usable = {
        i for i, v in enumerate(validities)
        if v.quality_by_domain.get("thermal") not in validity.BLOCKING_SEVERITIES
        and v.quality_by_domain.get("producer") not in validity.BLOCKING_SEVERITIES
        and v.quality_by_domain.get("sequence") not in validity.BLOCKING_SEVERITIES
    }
    sources = list(sources or [])
    if not sources:
        raise ExportError(f"{run_label}: no source provenance supplied; export would be unpinned")
    boot_ids = sorted({str(f.boot_id) for f in frames if f.boot_id})
    run_ids = sorted({str(f.run_id) for f in frames if f.run_id})
    boot_identity = boot_identity or {}

    if len(run_ids) == 1:
        run_id, run_id_status = run_ids[0], RUN_ID_SINGLE
    elif run_ids:
        # One boot_id carrying several device run_id segments is a segmentation
        # question, not two runs: publishing a synthetic joined ID would hand B a
        # key that exists in no source, and registering the segments separately
        # would overstate the run count. Both are refused - the export names the
        # segments and states that none of them is a certified run_id.
        run_id, run_id_status = None, RUN_ID_AMBIGUOUS
    else:
        run_id, run_id_status = None, RUN_ID_ABSENT
    if len(boot_ids) == 1:
        boot_id, boot_id_status = boot_ids[0], BOOT_ID_SINGLE
    elif boot_ids:
        boot_id, boot_id_status = None, BOOT_ID_AMBIGUOUS
    else:
        boot_id, boot_id_status = None, BOOT_ID_ABSENT

    device_ids = sorted({str(f.values["device_id"]) for f in frames if f.values.get("device_id")})
    # Computed before the rows, because the row contract says every row carries
    # them and a row cannot carry something that is only decided after it.
    run_identity = {
        "device_id": device_ids[0] if device_ids else "NOT_CARRIED_BY_THIS_ENCODING",
        "hardware_config_id": (
            boot_identity.get("hardware_config_id")
            or next((f.values.get("hardware_config_id") for f in frames
                     if f.values.get("hardware_config_id")), None)
            or "CG-HW-001"
        ),
        "firmware_version": (
            boot_identity.get("firmware_version")
            or next((f.values.get("firmware_version") for f in frames
                     if f.values.get("firmware_version")), None)
            or "NOT_CARRIED_BY_THIS_ENCODING"
        ),
    }
    sensors = sensors_block(frames, boot_identity)
    probe_roms = {entry["raw_slot"]: entry["rom"] for entry in sensors}
    export = {
        "run_id": run_id,
        "run_id_status": run_id_status,
        "device_run_label": run_label,
        "boot_id": boot_id,
        "boot_id_status": boot_id_status,
        "boot_ids": boot_ids,
        "run_ids": run_ids,
        "device_id": run_identity["device_id"],
        "hardware_config_id": run_identity["hardware_config_id"],
        "firmware_version": run_identity["firmware_version"],
        "schema_version": frames[0].values.get("schema"),
        "scenario_candidate": scenario_candidate,
        "scenario_candidate_basis": (
            "a candidate, not a certified run: docs/03 §31 defines the scenario and this export "
            "only states that the capture is compatible with it"
        ),
        "experiment_phase": {
            "per_frame_field": "frames[].experiment_phase",
            "counts": _phase_counts(frames),
        },
        "sensors": sensors,
        "timestamp_semantics": {**TIMESTAMP_SEMANTICS},
        "uptime_semantics": {
            "field": "device_ms",
            "meaning": "ESP32 uptime since this boot_id; not a wall clock",
            "resets_on": "every boot - opening the monitor port resets the board and changes boot_id",
            "cross_join_rule": "join on (device_id, boot_id, seq); never on device_ms alone",
            "doc_anchor": "docs/02 §4.2/§4.3",
        },
        "cadence": {
            "declared_hz": cadence_hz,
            "evidence": "device_ms successive deltas and seq monotonicity",
            "measured": measured_cadence(frames),
        },
        "frames": frame_rows(frames, validities, run_identity=run_identity,
                             probe_roms=probe_roms),
        "row_contract": row_contract_block(),
        "per_field_quality": per_field_quality(frames),
        "invalidation": {
            "summary": validity.summarize(validities),
            "rows_usable_for_this_scenarios_required_domains": len(usable),
            "rows_thermally_usable": len(thermal_usable),
            "policy": "no row is deleted; every row keeps its reason codes (docs/05A §18 A-W09-03)",
        },
        "derived_thermal_states": derived_thermal_states(frames, thermal_usable),
        "provenance": {
            "sources": [source.as_dict() for source in sources],
            "ingested_at_utc": generated_at_utc or utc_now_stamp(),
            "ingestion_host_clock": "HOST - the device cannot state an ingestion time",
            "export_version": EXPORT_VERSION,
            "notes": list(extra_notes or []),
        },
        "is_physical_measurement": True,
        "status_label": status_label,
        "export_version": EXPORT_VERSION,
    }
    _assert_complete(export)
    return export


def _phase_counts(frames: list[Frame]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for frame in frames:
        phase = classify_phase(frame)
        counts[phase] = counts.get(phase, 0) + 1
    return counts


def measured_cadence(frames: list[Frame]) -> dict:
    deltas = []
    ordered = [f for f in frames if isinstance(f.values.get("device_ms"), int)]
    for first, second in zip(ordered, ordered[1:]):
        if first.boot_id != second.boot_id:
            continue
        deltas.append(second.values["device_ms"] - first.values["device_ms"])
    if not deltas:
        return {"n_intervals": 0}
    return {
        "n_intervals": len(deltas),
        "mean_interval_ms": round(statistics.fmean(deltas), 3),
        "median_interval_ms": float(statistics.median(deltas)),
        "min_interval_ms": min(deltas),
        "max_interval_ms": max(deltas),
        "nonpositive_intervals": sum(1 for d in deltas if d <= 0),
    }


def build_run_index(
    runs: list[dict],
    *,
    generated_at_utc: str | None = None,
    notes: list[str] | None = None,
) -> dict:
    """The index W09 publishes and W10/W11 reuse.

    Member B's handoff is a list of *valid* run IDs; the index is what makes that
    list auditable - it states per run how many frames were usable and why the
    rest were not, so a candidate never silently becomes a valid run.
    """
    entries = []
    for run in runs:
        summary = run["invalidation"]["summary"]
        entries.append({
            "run_id": run["run_id"],
            "run_id_status": run["run_id_status"],
            "run_ids": list(run.get("run_ids") or []),
            "boot_id": run["boot_id"],
            "boot_id_status": run["boot_id_status"],
            "device_run_label": run.get("device_run_label"),
            "device_id": run["device_id"],
            "hardware_config_id": run["hardware_config_id"],
            "firmware_version": run["firmware_version"],
            "scenario_candidate": run["scenario_candidate"],
            "frames_total": summary["rows_total"],
            "frames_usable_for_baseline": summary["rows_usable_for_baseline"],
            # Named apart on purpose: the thermally-usable count is the row set the
            # thermal statistics are computed over, and it is not the same claim as
            # "usable for the S1 scenario" (docs/01 §20.1 on partial figures).
            "frames_thermally_usable_for_statistics":
                summary["rows_thermally_usable_for_statistics"],
            "frames_usable_per_scenario": summary["rows_usable_per_scenario"],
            "usable_fraction": summary["usable_fraction"],
            "quality_counts": summary["quality_counts"],
            "quality_counts_by_domain": summary["quality_counts_by_domain"],
            "top_invalidation_reasons": dict(sorted(
                summary["reason_counts"].items(), key=lambda kv: (-kv[1], kv[0])
            )),
            "is_physical_measurement": run["is_physical_measurement"],
            "status_label": run["status_label"],
            "source_paths": [s["path"] for s in run["provenance"]["sources"]],
            "source_sha256": {s["path"]: s["sha256"] for s in run["provenance"]["sources"]},
        })
    valid = [e for e in entries if e["usable_fraction"] and e["usable_fraction"] >= 0.5
             and e["is_physical_measurement"]
             and e["run_id_status"] == RUN_ID_SINGLE
             and e["boot_id_status"] == BOOT_ID_SINGLE]
    blocked = []
    for e in entries:
        reasons = []
        if e["run_id_status"] != RUN_ID_SINGLE:
            reasons.append(
                f"run_id_status={e['run_id_status']}: source run_id segments "
                f"{e['run_ids']} under one boot_id are not independent runs and no joined "
                "run_id exists in the source, so none can be published for a join"
            )
        if e["boot_id_status"] != BOOT_ID_SINGLE:
            reasons.append(f"boot_id_status={e['boot_id_status']}")
        if not e["is_physical_measurement"]:
            reasons.append("host fixture, not a physical measurement")
        if not (e["usable_fraction"] and e["usable_fraction"] >= 0.5):
            reasons.append("majority of frames unusable")
        if reasons:
            blocked.append({"run_id": e["run_id"], "device_run_label": e["device_run_label"],
                            "boot_id": e["boot_id"], "reasons": reasons,
                            "usable_fraction": e["usable_fraction"]})
    return {
        "index_version": RUN_INDEX_VERSION,
        "runs_total": len(entries),
        "runs_usable_majority": len(valid),
        "dedup_key": ["device_id", "boot_id", "seq"],
        "keys_unique": len({(e["device_id"], e["boot_id"]) for e in entries}) == len(entries),
        "valid_s1_run_ids_for_member_b": [e["run_id"] for e in valid
                                          if e["scenario_candidate"].startswith("S1")],
        "blocked_run_ids": blocked,
        "runs": entries,
        "generated_at_utc": generated_at_utc or utc_now_stamp(),
        "notes": list(notes or []),
        "honesty": [
            "usable_fraction is measured, not assumed",
            "a run with a majority of unusable frames is not handed to B as a valid S1 ID",
            "a run whose source run_id is ambiguous is not handed to B either: no joined "
            "identifier is invented for it",
            "every source byte is SHA-256 pinned, so this index can be re-derived",
        ],
    }


def write_json(path: pathlib.Path, payload: dict) -> None:
    import json

    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                    newline="\n")


def load_json(path: pathlib.Path) -> dict:
    import json

    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
