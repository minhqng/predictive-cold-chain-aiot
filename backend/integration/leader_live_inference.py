"""Leader-owned live inference bridge for the frozen W15 artifact and for
explicitly selected demo model directories.

Fails closed: any model-input feature that the frozen CG-FEAT-1.0 registry
(or a selected model's explicit feature contract) cannot derive from real
device data stays missing, and scoring is refused. No value is ever imputed,
zero-filled or synthesized here.

Scoring is demo-only. The default W15 artifact is synthetic-trained and
NON_DEPLOYABLE_CANDIDATE; a selected model directory may declare a different
training class, but this module never registers, promotes or persists a
prediction, and never claims field accuracy, calibration or control causality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "ml" / "src"))

from coldguard_backend.inference import (  # noqa: E402
    FrozenModel, FrozenModelSpec, InferenceUnavailable, load_frozen_model,
)

REGISTRY_PATH = REPO_ROOT / "ml" / "feature-registry-v1.yaml"
DEFAULT_FORECAST_DIR = REPO_ROOT / "ml/reports/W15/model"
LEGACY_MODEL_DIR = REPO_ROOT / "ml" / "reports" / "W15" / "model"
# Backwards-compatible name used by earlier callers/tests.
MODEL_DIR = LEGACY_MODEL_DIR
MODEL_DIR_ENV = "COLDGUARD_DEMO_MODEL_DIR"
MODEL_VERSION_ENV = "COLDGUARD_DEMO_MODEL_VERSION"

CHAMBER_FIELDS = ("t1_c", "t3_c", "t4_c")  # CENTER, BOTTOM, NEAR_DOOR
# role_map.observed_rig: t1=CHAMBER_CENTER t2=TEC_HOT_SIDE t3=CHAMBER_BOTTOM t4=CHAMBER_NEAR_DOOR.
# t4 source: Member A's frozen as-built assigns the SPARE ROM to CHAMBER_NEAR_DOOR
# (firmware/main/coldguard_config.h:282-284, evidence/A/W07/probe-identification-v0.md),
# and the device frame transports its reading as raw_spare_c. The mapping is
# bound to the delivered host role authority cg_probe_roles / position_of_rom
# and refuses any other ROM.
FEATURES = (
    "T_chamber_max_c", "T_chamber_min_c", "T_chamber_mean_c", "T_chamber_spread_c",
    "T_center_c", "T_bottom_c", "T_near_door_c",
    "rolling_mean_temperature_60s", "rolling_std_temperature_60s",
    "rolling_min_temperature_60s", "rolling_max_temperature_60s",
    "past_only_slope_c_per_min_60s", "past_only_temperature_delta_60s",
    "past_only_spatial_spread_60s",
    "door_open", "time_since_open", "duration_so_far", "count_past_60s",
    "applied_cooling", "applied_duty", "time_since_confirmed_applied_change",
    "cooling_voltage_v", "cooling_current_a", "cooling_power_w", "energy_counter_wh",
    "past_integrated_cooling_energy_wh",
    "ambient_temperature_c", "relative_humidity_pct",
)
MAX_GAP_S = 5.0
ROLLBACK_S = 60.0
# Freshness budget for presenting a score as current. Kept aligned with the
# dashboard's live-frame budget so a stale frame can never look live.
FRAME_MAX_AGE_S = 15.0
# Bounded current-boot history. At the delivered 1 Hz rate this covers more
# than five hours; refusing beyond it is safer than silently truncating the
# lifetime context this module depends on.
MAX_BOOT_ROWS = 20000
DOOR_RAW_OPEN = 1  # owner live observation 2026-11-13: raw 0 = CLOSED, raw 1 = OPEN
DOOR_POLARITY_RULE = (
    "raw 0 = CLOSED, raw 1 = OPEN (owner live observation 2026-11-13; "
    "per-boot attestation, never carried across boots)"
)

_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: dict[tuple, FrozenModel] = {}


class FeatureIncomplete(ValueError):
    def __init__(self, missing: list[str]) -> None:
        super().__init__("feature vector incomplete: " + ", ".join(missing))
        self.missing = sorted(missing)


@dataclass
class Row:
    """One normalized device sample, anchored on backend received time (UTC)."""

    received_at: datetime
    boot_id: str
    t1_c: float | None
    t3_c: float | None
    t4_c: float | None
    t_air_c: float | None
    rh_pct: float | None
    door_state: str | None
    thermal_valid: bool
    environment_valid: bool
    electrical_valid: bool
    applied_cooling: str | None
    applied_duty: float | None
    cooling_voltage_v: float | None
    cooling_current_a: float | None
    cooling_power_w: float | None
    energy_counter_wh: float | None
    # Parsed from the original serial frame (never guessed from raw polarity).
    door_raw: int | None = None
    door_status: str | None = None
    door_quality: str | None = None
    door_transitions: int | None = None
    door_open_firmware: float | None = None
    seq: int | None = None


@dataclass(frozen=True)
class ModelContract:
    directory: Path
    manifest_path: Path
    artifact_path: Path
    feature_schema_path: Path
    model_version: str
    feature_version: str
    artifact_sha256: str
    feature_schema_sha256: str
    feature_names: tuple[str, ...]
    horizon_s: int
    training_class: str
    data_evidence_class: str
    release_eligibility: str
    target: str | None
    horizon_status: str | None
    model_library_version: str | None
    model_task: str
    objective: str | None
    target_transform: str | None
    baseline_feature_id: str | None
    raw_native_load_prohibited: bool
    is_legacy: bool


def _num(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        out = _num(value)
        return int(out) if out is not None else None


def parse_device_frame(frame_text: str) -> dict:
    """Member A's delivered parser, reused verbatim (no member file touched)."""
    from firmware.tools.cg_telemetry_schema import parse_line

    return parse_line(frame_text).fields


def t4_from_device_frame(fields: dict | None) -> float | None:
    """CHAMBER_NEAR_DOOR reading from the spare slot, ROM-authority bound.

    Only raw_spare_status=OK and a spare ROM that Member A's frozen host role
    authority maps to CHAMBER_NEAR_DOOR may contribute; anything else fails
    closed (missing), never substitutes another probe.
    """
    if not fields:
        return None
    if fields.get("raw_spare_status") != "OK" or not isinstance(fields.get("spare_rom"), str):
        return None
    from firmware.tools.cg_telemetry_schema import position_of_rom

    if position_of_rom(fields["spare_rom"]) != "CHAMBER_NEAR_DOOR":
        return None
    return _num(fields.get("raw_spare_c"))


def row_from_mapping(m: dict) -> Row:
    received = m.get("backend_received_at") or m.get("received_at")
    if isinstance(received, str):
        received = datetime.fromisoformat(received)
    if received is None:
        raise ValueError("row has no backend_received_at anchor")
    if received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    frame_fields = None
    if m.get("raw_frame"):
        try:
            frame_fields = parse_device_frame(m["raw_frame"])
        except Exception:
            frame_fields = None
    return Row(
        received_at=received,
        boot_id=str(m.get("boot_id") or ""),
        t1_c=_num(m.get("t1_c")),
        t3_c=_num(m.get("t3_c")),
        # t4 (CHAMBER_NEAR_DOOR) arrives only via the device frame's spare
        # slot, ROM-bound to Member A's frozen as-built authority.
        t4_c=t4_from_device_frame(frame_fields) if frame_fields else _num(m.get("t4_c")),
        t_air_c=_num(m.get("t_air_c")),
        rh_pct=_num(m.get("rh_pct")),
        door_state=m.get("door_state"),
        thermal_valid=m.get("thermal_quality") == "VALID",
        environment_valid=m.get("environment_quality") == "VALID",
        electrical_valid=(m.get("electrical_quality") == "VALID" and m.get("cooling_energy_counter_wh") != "UNKNOWN"),
        applied_cooling=m.get("applied_cooling"),
        applied_duty=_num(m.get("applied_duty")),
        cooling_voltage_v=_num(m.get("cooling_voltage_v")),
        cooling_current_a=_num(m.get("cooling_current_a")),
        cooling_power_w=_num(m.get("cooling_power_w")),
        energy_counter_wh=_num(m.get("cooling_energy_counter_wh")),
        door_raw=_int(frame_fields.get("door_raw")) if frame_fields else None,
        door_status=frame_fields.get("door_status") if frame_fields else None,
        door_quality=frame_fields.get("door_quality") if frame_fields else None,
        door_transitions=_int(frame_fields.get("door_transitions")) if frame_fields else None,
        door_open_firmware=_num(frame_fields.get("door_open")) if frame_fields else None,
        seq=_int(m.get("seq")),
    )


def _chamber_mean(r: Row) -> float | None:
    probes = [r.t1_c, r.t3_c, r.t4_c]
    if not r.thermal_valid or any(v is None for v in probes):
        return None
    return sum(probes) / 3.0


def _chamber_spread(r: Row) -> float | None:
    probes = [r.t1_c, r.t3_c, r.t4_c]
    if not r.thermal_valid or any(v is None for v in probes):
        return None
    return max(probes) - min(probes)


def _weighted(values: list[tuple[float, float]]) -> float:
    # Left-hold weighting per registry (t - lookback, t].
    total_w = sum(w for _, w in values)
    return sum(v * w for v, w in values) / total_w


def _coverage(rows: list[Row]) -> tuple[list[Row], float, datetime] | None:
    """Samples fully inside the causal window with chamber coverage."""
    if not rows:
        return None
    anchor = rows[-1]
    start_metric = anchor.received_at - timedelta(seconds=ROLLBACK_S)
    window = [r for r in rows if start_metric < r.received_at <= anchor.received_at]
    if not window or window[0].received_at > start_metric + timedelta(seconds=MAX_GAP_S):
        return None  # minimum 60 s covered history not met
    for r in window:
        if _chamber_mean(r) is None:
            return None
    return window, ROLLBACK_S, anchor.received_at


def _time_weighted_rolls(window: list[Row]) -> tuple[float, float, float, float] | None:
    means = [(_chamber_mean(r), r) for r in window]
    segs = []
    for idx, (mu, row) in enumerate(means):
        prev = means[idx - 1][1].received_at if idx else window[-1].received_at - timedelta(seconds=ROLLBACK_S)
        w = (row.received_at - prev).total_seconds()
        if idx and w > MAX_GAP_S:
            return None
        segs.append((mu, w))
    mu = _weighted(segs)
    var = sum(w * (m - mu) ** 2 for m, w in segs) / sum(w for _, w in segs)
    return mu, math.sqrt(var), min(m for m, _ in segs), max(m for m, _ in segs)


def _slope(window: list[Row]) -> float | None:
    if len(window) < 3:
        return None
    t0 = window[0].received_at
    xs = [(r.received_at - t0).total_seconds() for r in window]
    ys = [_chamber_mean(r) for r in window]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom * 60.0


def _door_evidence(rows: list[Row], anchor: Row) -> dict:
    """Trusted per-boot door evidence, including lifetime opening context.

    Trust rules (registry CG-FEAT-1.0 `door_trust_rule`):
      * state must be OPEN or CLOSED (UNKNOWN is missing, never CLOSED);
      * the original serial frame must report door_status=OK and
        door_quality=VALID when those fields are present;
      * the boot must be attested by BOTH raw levels appearing in THIS boot,
        or by the device's own door_transitions counter being non-zero;
      * any frame whose firmware door_open disagrees with the delivered
        normalized state marks the boot untrusted (the earlier inverted
        mapping is refused rather than guessed around).
    Polarity is never inferred from a lone raw level.
    """
    raw_levels: set[int] = set()
    max_transitions = 0
    conflict = False
    for r in rows:
        if r.door_raw in (0, 1):
            raw_levels.add(r.door_raw)
        if r.door_transitions is not None:
            max_transitions = max(max_transitions, r.door_transitions)
        if (r.door_state in ("OPEN", "CLOSED") and r.door_open_firmware is not None):
            expected = 1.0 if r.door_state == "OPEN" else 0.0
            if int(r.door_open_firmware != 0) != int(expected):
                conflict = True
    attested = raw_levels == {0, 1} or max_transitions >= 1
    out = {
        "attested_this_boot": attested,
        "mapping_conflict": conflict,
        "raw_levels_this_boot": sorted(raw_levels),
        "transitions_counter": max_transitions,
        "polarity_rule": DOOR_POLARITY_RULE,
        "anchor_state": None,
        "duration_so_far": None,
        "time_since_open": None,
        "opening_edges": [],
    }
    if not attested or conflict:
        return out

    prev: float | None = None
    open_start: datetime | None = None
    last_state: tuple[datetime, float] | None = None
    opening_edges: list[datetime] = []
    for r in rows:
        state: float | None = None
        if r.door_state in ("OPEN", "CLOSED"):
            # Original-frame evidence is mandatory: a missing/untrusted
            # door_status or door_quality is missing, never a guess.
            if r.door_quality != "VALID" or r.door_status != "OK":
                state = None
            else:
                state = 1.0 if r.door_state == "OPEN" else 0.0
        if state is None:
            # An UNKNOWN/untrusted interruption breaks the current open
            # interval; nothing is bridged across it.
            prev = None
            open_start = None
            continue
        if prev is None:
            open_start = r.received_at if state == 1.0 else None
        elif prev == 0.0 and state == 1.0:
            opening_edges.append(r.received_at)
            open_start = r.received_at
        elif prev == 1.0 and state == 0.0:
            open_start = None
        prev = state
        last_state = (r.received_at, state)

    anchor_state = None
    if last_state is not None and last_state[0] == anchor.received_at:
        anchor_state = last_state[1]
    duration = None
    if anchor_state == 0.0:
        duration = 0.0
    elif anchor_state == 1.0 and open_start is not None:
        duration = (anchor.received_at - open_start).total_seconds()
    out.update({
        "anchor_state": anchor_state,
        "duration_so_far": duration,
        "time_since_open": (
            (anchor.received_at - opening_edges[-1]).total_seconds()
            if opening_edges else None
        ),
        "opening_edges": opening_edges,
    })
    return out


def compute_features(rows_in: list[Row]) -> dict[str, float | None]:
    """Compute CF-FEAT-1.0 features for the anchor = freshest row. Honest missing."""
    if not rows_in:
        raise FeatureIncomplete(FEATURES)
    rows = sorted(rows_in, key=lambda r: (r.boot_id, r.received_at, r.seq if r.seq is not None else -1))
    # The anchor boot is the FRESHEST boot by backend receive time, never a
    # lexicographic boot-id maximum: ids are unrelated hex tokens, so a
    # just-rebooted device would otherwise lose its freshest rows to an older
    # boot whose id happens to sort higher.
    anchor = max(rows, key=lambda r: (r.received_at, r.seq if r.seq is not None else -1))
    boot = anchor.boot_id
    same_boot = [r for r in rows if r.boot_id == boot]
    out: dict[str, float | None] = {}

    # Instantaneous chamber/role probes
    for fid, value in (
        ("T_center_c", anchor.t1_c if anchor.thermal_valid else None),
        ("T_bottom_c", anchor.t3_c if anchor.thermal_valid else None),
        ("T_near_door_c", anchor.t4_c if anchor.thermal_valid else None),
        ("T_chamber_max_c", None if _chamber_mean(anchor) is None else max(anchor.t1_c, anchor.t3_c, anchor.t4_c)),
        ("T_chamber_min_c", None if _chamber_mean(anchor) is None else min(anchor.t1_c, anchor.t3_c, anchor.t4_c)),
        ("T_chamber_mean_c", _chamber_mean(anchor)),
        ("T_chamber_spread_c", _chamber_spread(anchor)),
    ):
        out[fid] = value

    # Rolling 60 s family
    covered = _coverage(same_boot)
    if covered is None:
        out.update({k: None for k in (
            "rolling_mean_temperature_60s", "rolling_std_temperature_60s",
            "rolling_min_temperature_60s", "rolling_max_temperature_60s",
            "past_only_slope_c_per_min_60s", "past_only_temperature_delta_60s",
            "past_only_spatial_spread_60s",
        )})
    else:
        window, _, _t = covered
        rolls = _time_weighted_rolls(window)
        if rolls is None:
            out.update({k: None for k in (
                "rolling_mean_temperature_60s", "rolling_std_temperature_60s",
                "rolling_min_temperature_60s", "rolling_max_temperature_60s",
                "past_only_spatial_spread_60s", "past_only_temperature_delta_60s",
                "past_only_slope_c_per_min_60s",
            )})
        else:
            mu, std, tmin, tmax = rolls
            spreads = [(_chamber_spread(r), r.received_at) for r in window]
            for fid, val in (
                ("rolling_mean_temperature_60s", mu),
                ("rolling_std_temperature_60s", std),
                ("rolling_min_temperature_60s", tmin),
                ("rolling_max_temperature_60s", tmax),
                ("past_only_slope_c_per_min_60s", _slope(window)),
                ("past_only_temperature_delta_60s", _chamber_mean(window[-1]) - _chamber_mean(window[0])),
                ("past_only_spatial_spread_60s", _weighted([
                    (s, (window[i].received_at - (window[i - 1].received_at if i else window[-1].received_at - timedelta(seconds=ROLLBACK_S))).total_seconds())
                    for i, (s, _) in enumerate(spreads)
                ])),
            ):
                out[fid] = val

    # Door context: lifetime opening edges and the current interval come from
    # the whole current boot, not the 240-row tail that used to lose them.
    door = _door_evidence(same_boot, anchor)
    out["door_open"] = door["anchor_state"]
    out["time_since_open"] = door["time_since_open"]
    out["duration_so_far"] = door["duration_so_far"]
    out["count_past_60s"] = float(sum(
        1 for t in door["opening_edges"]
        if 0.0 < (anchor.received_at - t).total_seconds() <= 60.0
    ))

    # Actuation context (real device-reported edge state), full-boot history.
    out["applied_cooling"] = {"ON": 1.0, "OFF": 0.0}.get(anchor.applied_cooling or "")
    anchor_pair_ok = anchor.applied_cooling in ("ON", "OFF") and anchor.applied_duty is not None
    out["applied_duty"] = anchor.applied_duty if anchor_pair_ok else None
    changes: list[datetime] = []
    last = None
    for r in same_boot:
        if r.applied_cooling in ("ON", "OFF") and r.applied_duty is not None:
            pair = (r.applied_cooling, float(r.applied_duty))
            if last is not None and pair != last:
                changes.append(r.received_at)
            last = pair
    out["time_since_confirmed_applied_change"] = (
        (anchor.received_at - changes[-1]).total_seconds()
        if changes and anchor_pair_ok else None
    )

    # Electrical: only VALID quality ever promotes a numeric value.
    for fid, value in (
        ("cooling_voltage_v", anchor.cooling_voltage_v),
        ("cooling_current_a", anchor.cooling_current_a),
        ("cooling_power_w", anchor.cooling_power_w),
    ):
        out[fid] = value if anchor.electrical_valid else None

    # Energy register: VALID and non-decreasing within this boot.
    counter_ok = True
    previous_counter = None
    for r in same_boot:
        if not r.electrical_valid:
            continue
        if r.energy_counter_wh is None:
            counter_ok = False
            break
        if previous_counter is not None and r.energy_counter_wh < previous_counter:
            counter_ok = False
            break
        previous_counter = r.energy_counter_wh
    out["energy_counter_wh"] = (
        anchor.energy_counter_wh
        if anchor.electrical_valid and counter_ok and anchor.energy_counter_wh is not None
        else None
    )

    # Left-rectangle integration since the first VALID sample of this boot.
    # Every contributing interval must be VALID and <= max_gap_s; never bridged.
    out["past_integrated_cooling_energy_wh"] = None
    first_valid = next((i for i, r in enumerate(same_boot)
                        if r.electrical_valid and r.cooling_power_w is not None), None)
    if first_valid is not None and anchor.electrical_valid and anchor.cooling_power_w is not None:
        integrated = 0.0
        intervals = 0
        ok = True
        for prev, cur in zip(same_boot[first_valid:], same_boot[first_valid + 1:]):
            if not (prev.electrical_valid and prev.cooling_power_w is not None):
                ok = False
                break
            gap = (cur.received_at - prev.received_at).total_seconds()
            if gap <= 0 or gap > MAX_GAP_S:
                ok = False
                break
            integrated += prev.cooling_power_w * gap / 3600.0
            intervals += 1
        if ok and intervals:
            out["past_integrated_cooling_energy_wh"] = integrated

    # Environment (BME280)
    out["ambient_temperature_c"] = anchor.t_air_c if anchor.environment_valid else None
    out["relative_humidity_pct"] = anchor.rh_pct if anchor.environment_valid else None
    return out


def door_context(rows_in: list[Row]) -> dict:
    """Expose the trusted door evidence used by the feature vector."""
    if not rows_in:
        return {"attested_this_boot": False, "mapping_conflict": False,
                "anchor_state": None, "time_since_open": None,
                "duration_so_far": None, "opening_edges": [],
                "polarity_rule": DOOR_POLARITY_RULE}
    anchor = max(rows_in, key=lambda r: (r.received_at, r.seq if r.seq is not None else -1))
    rows = sorted(rows_in, key=lambda r: (r.boot_id, r.received_at, r.seq if r.seq is not None else -1))
    same_boot = [r for r in rows if r.boot_id == anchor.boot_id]
    out = _door_evidence(same_boot, anchor)
    out["opening_edges"] = [t.isoformat() for t in out["opening_edges"]]
    return out


def canonical_feature_schema(registry_path: Path = REGISTRY_PATH, directory: Path | None = None) -> tuple[Path, str, str]:
    """Derive the canonical schema file Member B's loader checks (hash-verified)."""
    try:
        import yaml
    except ImportError as exc:
        raise InferenceUnavailable("PyYAML is required for the legacy feature registry") from exc
    payload = yaml.safe_load(registry_path.read_bytes())
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    sha = hashlib.sha256(canonical).hexdigest()
    target = (directory or Path(tempfile.gettempdir())) / f"feature-registry-canonical-{sha[:12]}.json"
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != sha:
        target.write_bytes(canonical)
    return target, sha, payload["feature_version"]


def resolve_model_dir(model_dir: str | Path | None = None) -> Path:
    """Explicit argument > COLDGUARD_DEMO_MODEL_DIR > legacy W15 directory."""
    if model_dir is not None:
        return Path(model_dir).expanduser().resolve()
    env_dir = os.environ.get(MODEL_DIR_ENV)
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return LEGACY_MODEL_DIR


def _pick(mapping: dict, *keys, default=None):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def _manifest_path(directory: Path) -> Path:
    for name in ("model-manifest.json", "model-manifest-W15.json"):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    raise InferenceUnavailable(f"no model manifest in {directory}")


def _schema_hash_matches(path: Path, expected: str) -> bool:
    """Accept the file-byte hash or the trainer's canonical JSON hash.

    The legacy registry schema is emitted as compact canonical JSON, so its
    byte hash is canonical. The real-data trainer hashes
    ``json.dumps(parsed, sort_keys=True)`` (default separators); both bind the
    same ordered feature contract.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    if hashlib.sha256(raw).hexdigest() == expected:
        return True
    try:
        payload = json.loads(raw)
    except ValueError:
        return False
    canonical = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest() == expected


def _schema_feature_names(payload) -> list[str] | None:
    if isinstance(payload, list):
        return [str(x) for x in payload]
    if isinstance(payload, dict):
        for key in ("ordered_feature_ids", "orderedFeatureIds", "feature_names", "features"):
            value = payload.get(key)
            if isinstance(value, list):
                names = []
                for item in value:
                    if isinstance(item, str):
                        names.append(item)
                    elif isinstance(item, dict):
                        fid = _pick(item, "feature_id", "id", "name")
                        if fid is not None:
                            names.append(str(fid))
                    else:
                        return None
                return names
    return None


def _training_class(data_class: str | None) -> str:
    raw = (data_class or "").upper()
    if "SYNTHETIC" in raw:
        return "SYNTHETIC"
    if raw:
        return raw
    return "UNKNOWN"


def model_contract(model_dir: str | Path | None = None) -> ModelContract:
    """Read the selected directory's manifest and feature contract.

    Legacy W15 manifests keep their exact keys and registry-derived schema.
    A selected demo directory may use camelCase and supply feature-schema.json;
    its ordered features must be an explicit subset of the implemented
    FEATURES (unknown names are rejected, not silently dropped).
    """
    directory = resolve_model_dir(model_dir)
    manifest_path = _manifest_path(directory)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_version = str(_pick(manifest, "model_version", "modelVersion", "artifact_id", default=""))
    feature_version = str(_pick(manifest, "feature_version", "featureVersion", default=""))
    files = manifest.get("files") or {}
    ubj_file = files.get("ubj") if isinstance(files, dict) else None
    artifact_sha = str(_pick(
        manifest, "model_artifact_sha256", "artifact_sha256", "model_sha256",
        "modelSha256", default=(ubj_file or {}).get("sha256", ""),
    ))
    schema_sha = str(_pick(
        manifest, "feature_schema_hash", "feature_schema_sha256",
        "featureSchemaHash", "featureSchemaSha256", default="",
    ))
    raw_names = _pick(manifest, "ordered_feature_ids", "orderedFeatureIds",
                      "feature_ids", "featureIds", "feature_names", "features",
                      default=None)
    if not isinstance(raw_names, list):
        raise InferenceUnavailable("model manifest has no ordered feature list")
    feature_names = tuple(str(x) for x in raw_names)
    horizon_raw = _pick(manifest, "horizon_s", "horizonS", "horizon_seconds",
                        "target_horizon_s", "horizon", default=None)
    if horizon_raw is None:
        raise InferenceUnavailable("model manifest has no horizon")
    horizon_s = int(float(horizon_raw))
    if not model_version or not feature_version or not artifact_sha or not schema_sha:
        raise InferenceUnavailable("model manifest is missing version/hash fields")
    if not feature_names:
        raise InferenceUnavailable("model manifest feature list is empty")
    unknown = [fid for fid in feature_names if fid not in FEATURES]
    if unknown:
        raise InferenceUnavailable(
            "model manifest requires unimplemented features: " + ", ".join(unknown))
    if len(set(feature_names)) != len(feature_names):
        raise InferenceUnavailable("model manifest feature list has duplicates")

    feature_schema = directory / "feature-schema.json"
    if feature_schema.is_file():
        if not _schema_hash_matches(feature_schema, schema_sha):
            raise InferenceUnavailable("feature-schema.json checksum mismatch")
        try:
            schema_payload = json.loads(feature_schema.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise InferenceUnavailable("feature-schema.json is not valid JSON") from exc
        schema_names = _schema_feature_names(schema_payload)
        if schema_names is not None and tuple(schema_names) != feature_names:
            raise InferenceUnavailable("feature-schema.json order disagrees with manifest")
    else:
        canonical_path, canonical_sha, _fv = canonical_feature_schema()
        if canonical_sha != schema_sha:
            raise InferenceUnavailable("legacy feature registry checksum mismatch")
        feature_schema = canonical_path

    artifact_path = directory / "model.ubj"
    if not artifact_path.is_file():
        raise InferenceUnavailable(f"model artifact missing in {directory}")

    data_class = str(_pick(manifest, "training_data_class", "data_evidence_class", default=""))
    model_task = str(_pick(manifest, "model_task", "task", default="risk_score"))
    objective = _pick(manifest, "objective")
    target_transform = _pick(manifest, "target_transform")
    baseline_feature_id = _pick(manifest, "baseline_feature_id")
    if model_task == "temperature_forecast":
        if objective != "reg:squarederror":
            raise InferenceUnavailable("temperature forecast manifest objective must be reg:squarederror")
        if target_transform != "delta_from_current_chamber_mean":
            raise InferenceUnavailable(
                "temperature forecast target_transform must be delta_from_current_chamber_mean")
        if baseline_feature_id not in FEATURES:
            raise InferenceUnavailable("temperature forecast baseline feature is not implemented")
        if baseline_feature_id not in feature_names:
            raise InferenceUnavailable(
                "temperature forecast baseline feature is missing from ordered features")
        if bool(_pick(manifest, "raw_native_load_prohibited", default=True)):
            raise InferenceUnavailable(
                "temperature forecast manifest prohibits native regressor load")
    return ModelContract(
        directory=directory,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
        feature_schema_path=feature_schema,
        model_version=model_version,
        feature_version=feature_version,
        artifact_sha256=artifact_sha,
        feature_schema_sha256=schema_sha,
        feature_names=feature_names,
        horizon_s=horizon_s,
        training_class=_training_class(data_class),
        data_evidence_class=data_class or "UNKNOWN",
        release_eligibility=str(_pick(manifest, "release_eligibility", "eligibility", default="UNKNOWN")),
        target=_pick(manifest, "target", "target_spec_version", "target_id"),
        horizon_status=_pick(manifest, "horizon_status"),
        model_library_version=_pick(manifest, "model_library_version", "library_version"),
        model_task=model_task,
        objective=objective,
        target_transform=target_transform,
        baseline_feature_id=baseline_feature_id,
        raw_native_load_prohibited=bool(_pick(manifest, "raw_native_load_prohibited", default=True)),
        is_legacy=directory == LEGACY_MODEL_DIR,
    )


def model_metadata(model_dir: str | Path | None = None) -> dict:
    contract = model_contract(model_dir)
    notes = [
        "Demo-only shadow score; not persisted, not registered, and not promoted "
        "to production by this endpoint.",
    ]
    if contract.training_class == "SYNTHETIC":
        notes.append(
            "Selected artifact is synthetic-trained "
            f"({contract.data_evidence_class}); it is NOT field accuracy, "
            "calibration, early-warning or control-causality evidence.")
    else:
        notes.append(
            f"Selected artifact declares training_data_class="
            f"{contract.data_evidence_class}; no field accuracy, calibration or "
            "control-causality claim is made from this demo score.")
    if contract.release_eligibility != "NON_DEPLOYABLE_CANDIDATE":
        notes.append(
            f"Manifest release_eligibility={contract.release_eligibility}; this "
            "endpoint still does not register or deploy the artifact.")
    if contract.model_task == "temperature_forecast":
        notes.append(
            "Experimental demo temperature forecast (°C), not a probability, "
            "not field-accuracy or control-causality evidence, and not an "
            "actuation decision.")
    return {
        "mode": "DEMO_ONLY_SHADOW",
        "demo_only": True,
        "model_selection": "legacy_default" if contract.is_legacy else "explicit_model_dir",
        "model_dir": str(contract.directory),
        "model_version": contract.model_version,
        "artifact_sha256": contract.artifact_sha256,
        "feature_version": contract.feature_version,
        "feature_schema_sha256": contract.feature_schema_sha256,
        "feature_names": list(contract.feature_names),
        "feature_total": len(contract.feature_names),
        "horizon_s": contract.horizon_s,
        "horizon_status": contract.horizon_status,
        "target": contract.target,
        "training_class": contract.training_class,
        "training_data_class": contract.data_evidence_class,
        "release_eligibility": contract.release_eligibility,
        "model_library_version": contract.model_library_version,
        "model_task": contract.model_task,
        "objective": contract.objective,
        "target_transform": contract.target_transform,
        "baseline_feature_id": contract.baseline_feature_id,
        "raw_native_load_prohibited": contract.raw_native_load_prohibited,
        "unit": "degC" if contract.model_task == "temperature_forecast" else "risk_score",
        "notes": notes,
    }


def load_demo_model(model_version: str | None = None, model_dir: str | Path | None = None) -> FrozenModel:
    """Load a legacy risk classifier through the same hash-verified frozen loader.

    Temperature-forecast regressors deliberately take the separate
    `load_demo_regressor` path: their °C output must never pass through the
    legacy 0..1 risk validator.
    """
    contract = model_contract(model_dir)
    if contract.model_task == "temperature_forecast":
        raise InferenceUnavailable("temperature forecast model requires the regressor path")
    if model_version is not None and model_version != contract.model_version:
        raise InferenceUnavailable("requested model version does not match manifest")
    spec = FrozenModelSpec(
        model_version=contract.model_version,
        feature_version=contract.feature_version,
        artifact_sha256=contract.artifact_sha256,
        feature_schema_sha256=contract.feature_schema_sha256,
        feature_names=contract.feature_names,
        horizon_s=contract.horizon_s,
    )
    return load_frozen_model(
        contract.artifact_path, contract.feature_schema_path, manifest=spec, approved=spec,
    )


def load_w15_model(model_version: str, workdir: Path | None = None) -> FrozenModel:
    """Backwards-compatible legacy loader (default W15 directory)."""
    del workdir  # retained for callers; canonical schema now uses the temp default
    return load_demo_model(model_version, LEGACY_MODEL_DIR)


@dataclass(frozen=True)
class FrozenRegressor:
    """Own-trained temperature forecast regressor (°C delta output).

    This is intentionally separate from `FrozenModel`: the legacy risk
    validator's finite-[0,1] check must not be applied to a temperature delta.
    Artifact/schema hashes and feature order are verified before native load.
    """

    contract: ModelContract
    booster: object

    def predict(self, features: dict[str, float | None]) -> float:
        import xgboost as xgb  # noqa: PLC0415

        values = []
        for fid in self.contract.feature_names:
            value = features.get(fid)
            if value is None:
                raise FeatureIncomplete([fid])
            values.append(float(value))
        output = self.booster.predict(
            xgb.DMatrix([values], feature_names=list(self.contract.feature_names)),
            validate_features=True,
        )
        if output.shape != (1,):
            raise InferenceUnavailable("regressor did not return one forecast")
        delta = float(output[0])
        if not math.isfinite(delta):
            raise InferenceUnavailable("regressor forecast is not finite")
        return delta


def load_demo_regressor(model_dir: str | Path | None = None) -> FrozenRegressor:
    """Hash-verify UBJ/schema/order, then natively load the new regressor."""
    contract = model_contract(model_dir)
    if contract.model_task != "temperature_forecast":
        raise InferenceUnavailable("selected model is not a temperature forecast model")
    if contract.raw_native_load_prohibited:
        raise InferenceUnavailable("manifest prohibits native regressor load")
    try:
        artifact = contract.artifact_path.read_bytes()
    except OSError as exc:
        raise InferenceUnavailable("regressor artifact unavailable") from exc
    if hashlib.sha256(artifact).hexdigest() != contract.artifact_sha256:
        raise InferenceUnavailable("regressor artifact checksum mismatch")
    if not _schema_hash_matches(
            contract.feature_schema_path, contract.feature_schema_sha256):
        raise InferenceUnavailable("regressor feature schema checksum mismatch")
    try:
        import xgboost as xgb  # noqa: PLC0415
    except ImportError as exc:
        raise InferenceUnavailable("XGBoost runtime unavailable") from exc
    booster = xgb.Booster()
    try:
        booster.load_model(bytearray(artifact))
    except xgb.core.XGBoostError as exc:
        raise InferenceUnavailable("regressor artifact could not be loaded") from exc
    if booster.num_features() != len(contract.feature_names):
        raise InferenceUnavailable("regressor feature count mismatch")
    if booster.feature_names is not None and tuple(booster.feature_names) != contract.feature_names:
        raise InferenceUnavailable("regressor feature order mismatch")
    try:
        config = json.loads(booster.save_config())
        actual_objective = (config.get("learner") or {}).get("objective", {}).get("name")
    except (ValueError, AttributeError):
        actual_objective = None
    if actual_objective is not None and actual_objective != contract.objective:
        raise InferenceUnavailable("regressor objective disagrees with manifest")
    return FrozenRegressor(contract, booster)


_REGRESSOR_CACHE: dict[tuple, FrozenRegressor] = {}


def _cached_regressor(contract: ModelContract, model_version: str | None) -> FrozenRegressor:
    version = model_version or contract.model_version
    if version != contract.model_version:
        raise InferenceUnavailable("requested model version does not match manifest")
    try:
        stat = contract.artifact_path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError as exc:
        raise InferenceUnavailable("regressor artifact unavailable") from exc
    key = (str(contract.directory), version, contract.artifact_sha256, stamp)
    with _MODEL_LOCK:
        regressor = _REGRESSOR_CACHE.get(key)
        if regressor is None:
            regressor = load_demo_regressor(contract.directory)
            _REGRESSOR_CACHE[key] = regressor
        return regressor


def _cached_model(contract: ModelContract, model_version: str | None) -> FrozenModel:
    version = model_version or contract.model_version
    if version != contract.model_version:
        raise InferenceUnavailable("requested model version does not match manifest")
    try:
        stat = contract.artifact_path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError as exc:
        raise InferenceUnavailable("model artifact unavailable") from exc
    key = (str(contract.directory), version, contract.artifact_sha256, stamp)
    with _MODEL_LOCK:
        model = _MODEL_CACHE.get(key)
        if model is None:
            model = load_demo_model(version, contract.directory)
            _MODEL_CACHE[key] = model
        return model


def score_or_block(model: FrozenModel, features: dict[str, float | None]) -> dict:
    required = tuple(model.spec.feature_names)
    missing = [fid for fid in required if features.get(fid) is None]
    if missing:
        raise FeatureIncomplete(missing)
    predictor = model.score({fid: float(features[fid]) for fid in required})
    return {"risk": predictor, "feature_count": len(required)}


def _db_url() -> str | None:
    url = os.environ.get("DATABASE_URL")
    return url.replace("postgresql+psycopg", "postgresql") if url else None


_ANCHOR_SQL = """
SELECT last_boot_id AS boot_id, last_seq
FROM device_twin
WHERE device_id = %s AND last_boot_id IS NOT NULL
"""


_ROWS_SQL = """
SELECT t.backend_received_at, t.boot_id, t.seq, t.t1_c, t.t3_c, t.t_air_c, t.rh_pct,
       t.door_state, t.thermal_quality, t.environment_quality, t.electrical_quality,
       t.applied_cooling, t.applied_duty, t.cooling_voltage_v, t.cooling_current_a,
       t.cooling_power_w, t.cooling_energy_counter_wh,
       tr.raw_json->'serial_source'->>'frame' AS raw_frame,
       t.serial_source->>'gateway_received_at' AS gateway_received_at
FROM telemetry t
JOIN telemetry_raw tr ON tr.id = t.raw_id
WHERE t.device_id = %s AND t.boot_id = %s AND t.seq <= %s
  AND t.twin_eligible AND t.serial_source IS NOT NULL
ORDER BY t.backend_received_at ASC, t.seq ASC
LIMIT %s
"""


def fetch_current_boot_rows(device_id: str = "coldguard-001", db_url: str | None = None) -> list[dict]:
    """Read-only fetch of the freshest boot, bounded and gap-preserving.

    The whole current boot is fetched (not an arbitrary 240-row tail) because
    lifetime door-opening and applied-change context are required features.
    Older boots are segregated by the anchor boot_id. No row is synthesized;
    gaps and invalid rows remain in the returned list so the feature code can
    refuse them.
    """
    url = db_url or _db_url()
    if not url:
        raise InferenceUnavailable("database URL unavailable (DATABASE_URL)")
    import psycopg  # noqa: PLC0415 - lazy: dashboard stays importable without DB deps
    from psycopg.rows import dict_row  # noqa: PLC0415

    try:
        with psycopg.connect(url, connect_timeout=5, row_factory=dict_row) as conn:
            conn.read_only = True
            anchor = conn.execute(_ANCHOR_SQL, (device_id,)).fetchone()
            if not anchor:
                raise InferenceUnavailable("no telemetry rows for device")
            boot_id = anchor["boot_id"]
            rows = conn.execute(
                _ROWS_SQL, (device_id, boot_id, anchor["last_seq"], MAX_BOOT_ROWS + 1)
            ).fetchall()
    except psycopg.OperationalError as exc:
        raise InferenceUnavailable("database unreachable") from exc
    if len(rows) > MAX_BOOT_ROWS:
        raise InferenceUnavailable(
            f"current boot exceeds bounded history limit ({MAX_BOOT_ROWS} rows)")
    if not rows or rows[-1]["seq"] != anchor["last_seq"]:
        raise InferenceUnavailable("current Twin frame lacks matching real serial evidence")
    observed = datetime.fromisoformat(rows[-1]["gateway_received_at"])
    if not 0 <= (datetime.now(timezone.utc) - observed).total_seconds() <= FRAME_MAX_AGE_S:
        raise InferenceUnavailable("current Twin frame is stale")
    return [dict(r) for r in rows]


def _vector_sha(features: dict[str, float | None], names: tuple[str, ...]) -> str:
    payload = [[fid, features.get(fid)] for fid in names]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def live_prediction(
    device_id: str = "coldguard-001",
    model_version: str | None = None,
    model_dir: str | Path | None = None,
    *,
    rows: list[Row] | None = None,
    now: datetime | None = None,
    source: str | None = None,
) -> dict:
    """One read-only demo score for the freshest current-boot data.

    `rows` exists for unit tests only; callers that supply it must label the
    source themselves (defaults to UNIT_FIXTURE). Normal operation fetches the
    real current boot from the read-only database and labels it REAL_SERIAL.
    """
    now = now or datetime.now(timezone.utc)
    if rows is None:
        try:
            raw_rows = fetch_current_boot_rows(device_id)
        except Exception as exc:  # noqa: BLE001 - report the read-only refusal
            error = (str(exc) if type(exc).__name__ == "InferenceUnavailable"
                     else "database read failed")
            return {
                "mode": "DEMO_ONLY_SHADOW", "demo_only": True,
                "source": "REAL_SERIAL_UNAVAILABLE", "device_id": device_id,
                "score_status": "BLOCKED_DATABASE_UNAVAILABLE",
                "score": None, "missing_features": [], "feature_total": None,
                "feature_count": 0, "error": error,
                "note": "no score is presented; the read-only database is unavailable",
            }
        rows = [row_from_mapping(m) for m in raw_rows]
        source = source or "REAL_SERIAL"
    else:
        source = source or "UNIT_FIXTURE"
    if not rows:
        return {
            "mode": "DEMO_ONLY_SHADOW", "demo_only": True, "source": source,
            "device_id": device_id, "score_status": "BLOCKED_NO_ANCHOR",
            "score": None, "missing_features": [], "feature_total": None,
            "feature_count": 0,
        }

    try:
        contract = model_contract(model_dir)
    except InferenceUnavailable as exc:
        return {
            "mode": "DEMO_ONLY_SHADOW", "demo_only": True, "source": source,
            "device_id": device_id, "score_status": "BLOCKED_MODEL_UNAVAILABLE",
            "score": None, "missing_features": [], "feature_total": None,
            "feature_count": 0, "error": str(exc),
        }

    features = compute_features(rows)
    required = contract.feature_names
    missing = [fid for fid in required if features.get(fid) is None]
    anchor = max(rows, key=lambda r: (r.received_at, r.seq if r.seq is not None else -1))
    age_s = (now - anchor.received_at).total_seconds()
    vector = {fid: features.get(fid) for fid in required}
    door_rows = sorted(
        [r for r in rows if r.boot_id == anchor.boot_id],
        key=lambda r: (r.received_at, r.seq if r.seq is not None else -1),
    )
    door = _door_evidence(door_rows, anchor)
    try:
        metadata = model_metadata(model_dir)
    except InferenceUnavailable as exc:
        return {
            "mode": "DEMO_ONLY_SHADOW", "demo_only": True, "source": source,
            "device_id": device_id, "score_status": "BLOCKED_MODEL_UNAVAILABLE",
            "score": None, "missing_features": missing, "feature_total": None,
            "feature_count": 0, "error": str(exc),
        }
    is_forecast = contract.model_task == "temperature_forecast"
    payload = {
        **metadata,
        "source": source,
        "device_id": device_id,
        "score_status": None,
        "score": None,
        "feature_count": len(required) - len(missing),
        "missing_features": missing,
        "features": vector,
        "feature_vector_sha256": _vector_sha(features, required),
        "current_boot": anchor.boot_id,
        "anchor_utc": anchor.received_at.isoformat(),
        "anchor_seq": anchor.seq,
        "as_of_utc": now.isoformat(),
        "frame_age_s": round(age_s, 1),
        "fresh": 0 <= age_s <= FRAME_MAX_AGE_S,
        "door_attested_this_boot": door["attested_this_boot"],
        "door_mapping_conflict": door["mapping_conflict"],
        "door_polarity_rule": DOOR_POLARITY_RULE,
    }
    if is_forecast:
        payload.update({
            "forecast_status": None,
            "unit": "degC",
            "horizon_s": contract.horizon_s,
            "baseline_feature_id": contract.baseline_feature_id,
            "current_chamber_mean_c": None,
            "predicted_delta_c": None,
            "predicted_temperature_c": None,
        })
    if not payload["fresh"]:
        stale_status = "STALE_NO_FORECAST" if is_forecast else "STALE_NO_SCORE"
        payload["score_status"] = stale_status
        if is_forecast:
            payload["forecast_status"] = stale_status
        payload["note"] = (
            f"anchor age {age_s:.1f}s is outside [0, {FRAME_MAX_AGE_S:.0f}s]; no "
            f"{'forecast' if is_forecast else 'score'} is presented as current")
        return payload
    if missing:
        payload["score_status"] = "BLOCKED_FEATURES_INCOMPLETE"
        if is_forecast:
            payload["forecast_status"] = "BLOCKED_FEATURES_INCOMPLETE"
        payload["note"] = "required real features missing; scoring refused"
        return payload
    if is_forecast:
        try:
            regressor = _cached_regressor(contract, model_version)
            delta = regressor.predict(features)
            baseline = contract.baseline_feature_id or "T_chamber_mean_c"
            current = features.get(baseline)
            if current is None:
                raise FeatureIncomplete([baseline])
            predicted = float(current) + delta
            if not math.isfinite(predicted):
                raise InferenceUnavailable("forecast temperature is not finite")
        except (InferenceUnavailable, FeatureIncomplete) as exc:
            payload["score_status"] = "BLOCKED_MODEL_UNAVAILABLE"
            payload["forecast_status"] = "BLOCKED_MODEL_UNAVAILABLE"
            payload["error"] = str(exc)
            return payload
        payload.update({
            "score_status": "OK_EXPERIMENTAL_DEMO",
            "forecast_status": "OK_EXPERIMENTAL_DEMO",
            "current_chamber_mean_c": float(current),
            "predicted_delta_c": delta,
            "predicted_temperature_c": predicted,
            "unit": "degC",
            "horizon_s": contract.horizon_s,
            "baseline_feature_id": baseline,
            "note": (
                f"experimental demo forecast: current chamber mean + "
                f"{delta:+.2f} °C over {contract.horizon_s} s; no probability "
                "or accuracy claim"),
        })
        return payload
    try:
        model = _cached_model(contract, model_version)
        result = score_or_block(model, features)
    except (InferenceUnavailable, FeatureIncomplete) as exc:
        payload["score_status"] = "BLOCKED_MODEL_UNAVAILABLE"
        payload["error"] = str(exc)
        return payload
    payload["score_status"] = "OK_DEMO_ONLY"
    payload["score"] = result["risk"]
    payload["note"] = "real current-boot feature vector scored by the selected frozen artifact"
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Leader live inference (fail-closed, demo-only)")
    parser.add_argument("--device-id", default="coldguard-001")
    parser.add_argument("--model-version", default=None,
                        help="manifest model version; default = selected manifest")
    parser.add_argument("--model-dir", default=None,
                        help="demo model directory (default: $COLDGUARD_DEMO_MODEL_DIR or W15)")
    parser.add_argument("--window-s", type=int, default=90,
                        help="retained for CLI compatibility; the causal window is registry-defined")
    parser.add_argument("--offline-rows", default=None,
                        help="JSON rows file; skips database (unit/inspection only)")
    parser.add_argument("--score", action="store_true",
                        help="perform one real scoring call (read-only, no persistence)")
    args = parser.parse_args(argv)

    del args.window_s
    source = "OFFLINE_ROWS" if args.offline_rows else "REAL_SERIAL"

    if args.score:
        if args.offline_rows:
            raw_rows = json.loads(Path(args.offline_rows).read_text(encoding="utf-8"))
            rows = [row_from_mapping(r) for r in raw_rows]
            payload = live_prediction(
                args.device_id, args.model_version, args.model_dir,
                rows=rows, source=source)
        else:
            payload = live_prediction(
                args.device_id, args.model_version, args.model_dir)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0 if str(payload.get("score_status", "")).startswith("OK_") else 2

    if args.offline_rows:
        raw_rows = json.loads(Path(args.offline_rows).read_text(encoding="utf-8"))
        rows = [row_from_mapping(r) for r in raw_rows]
    else:
        try:
            raw_rows = fetch_current_boot_rows(args.device_id)
            rows = [row_from_mapping(r) for r in raw_rows]
        except Exception as exc:  # noqa: BLE001 - report the read-only refusal
            print(json.dumps({"verdict": "BLOCKED_DATABASE_UNAVAILABLE",
                              "error": f"{type(exc).__name__}: {exc}"}, indent=2))
            return 2

    features = compute_features(rows)
    try:
        contract = model_contract(args.model_dir)
        metadata = model_metadata(args.model_dir)
    except InferenceUnavailable as exc:
        print(json.dumps({"verdict": "BLOCKED_MODEL_UNAVAILABLE", "error": str(exc)},
                         indent=2))
        return 2
    required = contract.feature_names
    missing = sorted(fid for fid in required if features.get(fid) is None)
    anchor = max(rows, key=lambda r: (r.received_at, r.seq if r.seq is not None else -1))
    now = datetime.now(timezone.utc)
    age_s = (now - anchor.received_at).total_seconds()
    verdict = {
        "verdict": "BLOCKED_FEATURES_INCOMPLETE" if missing else "COMPUTE_COMPLETE",
        **metadata,
        "source": source,
        "feature_count": len(required) - len(missing),
        "feature_total": len(required),
        "missing_features": missing,
        "present_features": {f: features[f] for f in required if features.get(f) is not None},
        "current_boot": anchor.boot_id,
        "anchored_at": anchor.received_at.isoformat(),
        "as_of_utc": now.isoformat(),
        "frame_age_s": round(age_s, 1),
        "fresh": 0 <= age_s <= FRAME_MAX_AGE_S,
        "door": door_context(rows),
    }
    print(json.dumps(verdict, indent=2, ensure_ascii=True))
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
