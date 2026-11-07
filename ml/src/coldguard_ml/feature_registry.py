"""W10 feature registry loader and validator (B-W10-01).

The registry YAML is the frozen feature-schema identity. This module loads it
strictly, validates every entry, and computes the canonical SHA-256 recorded on
feature rows and artifacts. It deliberately freezes definitions only: physical
thresholds, the final representative temperature, the primary horizon and
other physical parameters stay outside this identity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

REGISTRY_SCHEMA = "coldguard-feature-registry-v1"
DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "feature-registry-v1.yaml"
)

FROZEN_DEFINITION = "FROZEN_DEFINITION"

FAMILY_INSTANTANEOUS_THERMAL = "instantaneous_thermal"
FAMILY_DIAGNOSTIC_THERMAL = "diagnostic_thermal"
FAMILY_ROLLING_THERMAL = "rolling_thermal"
FAMILY_DOOR = "door_context"
FAMILY_ACTUATION = "actuation_context"
FAMILY_ELECTRICAL = "electrical_context"
FAMILY_ENVIRONMENTAL = "environmental_context"
FAMILIES = (
    FAMILY_INSTANTANEOUS_THERMAL,
    FAMILY_DIAGNOSTIC_THERMAL,
    FAMILY_ROLLING_THERMAL,
    FAMILY_DOOR,
    FAMILY_ACTUATION,
    FAMILY_ELECTRICAL,
    FAMILY_ENVIRONMENTAL,
)

METHOD_INSTANTANEOUS_PROBE = "instantaneous_probe"
METHOD_INSTANTANEOUS_AGGREGATE = "instantaneous_aggregate"
METHOD_ROLLING_THERMAL = "rolling_thermal"
METHOD_DOOR_OPEN = "door_open"
METHOD_DOOR_TIME_SINCE_OPEN = "door_time_since_open"
METHOD_DOOR_DURATION = "door_duration_so_far"
METHOD_DOOR_COUNT = "door_count_past_60s"
METHOD_ACTUATION_STATE = "actuation_state"
METHOD_ACTUATION_DUTY = "actuation_duty"
METHOD_ACTUATION_SINCE_CHANGE = "actuation_since_change"
METHOD_ELECTRICAL_CHANNEL = "electrical_channel"
METHOD_INTEGRATED_POWER = "integrated_power"
METHOD_ENVIRONMENT_CHANNEL = "environment_channel"
METHODS = (
    METHOD_INSTANTANEOUS_PROBE,
    METHOD_INSTANTANEOUS_AGGREGATE,
    METHOD_ROLLING_THERMAL,
    METHOD_DOOR_OPEN,
    METHOD_DOOR_TIME_SINCE_OPEN,
    METHOD_DOOR_DURATION,
    METHOD_DOOR_COUNT,
    METHOD_ACTUATION_STATE,
    METHOD_ACTUATION_DUTY,
    METHOD_ACTUATION_SINCE_CHANGE,
    METHOD_ELECTRICAL_CHANNEL,
    METHOD_INTEGRATED_POWER,
    METHOD_ENVIRONMENT_CHANNEL,
)

AGGREGATE_STATISTICS = ("max", "min", "mean", "spread")
ROLLING_STATISTICS = (
    "time_weighted_mean",
    "time_weighted_std",
    "min",
    "max",
    "least_squares_slope",
    "delta",
    "time_weighted_spread",
)
ACTUATION_CHANNELS = ("requested", "applied", "readback")
ELECTRICAL_FIELDS = ("voltage_v", "current_a", "power_w", "counter_wh")
ENVIRONMENT_FIELDS = ("t_air_c", "rh_pct")

_FEATURE_KEYS = {
    "feature_id",
    "feature_name",
    "version",
    "dtype",
    "unit",
    "family",
    "physical_meaning",
    "source_fields",
    "source_schema",
    "sensor_roles",
    "quality_requirements",
    "time_domain",
    "lookback_rule",
    "lookback_s",
    "minimum_history_s",
    "max_gap_s",
    "missing_data_policy",
    "first_valid_timestamp_rule",
    "causal_availability_condition",
    "aggregation_definition",
    "method",
    "method_params",
    "provenance",
    "freeze_status",
    "intended_use",
}
_TOP_KEYS = {
    "schema",
    "feature_version",
    "registry_status",
    "frozen_scope",
    "not_frozen_here",
    "policy",
    "role_map",
    "features",
}
_POLICY_KEYS = {
    "window_convention",
    "minimum_history_rule",
    "max_gap_s",
    "duplicate_policy",
    "missing_data_policy",
    "time_domain_policy",
    "boot_boundary_policy",
    "fit_policy",
    "electrical_qualification",
    "door_trust_rule",
}


class FeatureRegistryError(ValueError):
    """The registry would not be a stable, explicit feature contract."""


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys."""


def _construct_mapping_no_duplicates(loader, node, deep=False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise FeatureRegistryError(
                f"duplicate registry key {key!r} at line {key_node.start_mark.line + 1}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_duplicates,
)


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    feature_name: str
    version: str
    dtype: str
    unit: str
    family: str
    physical_meaning: str
    source_fields: tuple[str, ...]
    source_schema: str
    sensor_roles: tuple[str, ...]
    quality_requirements: str
    time_domain: str
    lookback_rule: str
    lookback_s: float | None
    minimum_history_s: float
    max_gap_s: float | None
    missing_data_policy: str
    first_valid_timestamp_rule: str
    causal_availability_condition: str
    aggregation_definition: str
    method: str
    method_params: Mapping[str, str]
    provenance: str
    freeze_status: str
    intended_use: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_name": self.feature_name,
            "version": self.version,
            "dtype": self.dtype,
            "unit": self.unit,
            "family": self.family,
            "physical_meaning": self.physical_meaning,
            "source_fields": list(self.source_fields),
            "source_schema": self.source_schema,
            "sensor_roles": list(self.sensor_roles),
            "quality_requirements": self.quality_requirements,
            "time_domain": self.time_domain,
            "lookback_rule": self.lookback_rule,
            "lookback_s": self.lookback_s,
            "minimum_history_s": self.minimum_history_s,
            "max_gap_s": self.max_gap_s,
            "missing_data_policy": self.missing_data_policy,
            "first_valid_timestamp_rule": self.first_valid_timestamp_rule,
            "causal_availability_condition": self.causal_availability_condition,
            "aggregation_definition": self.aggregation_definition,
            "method": self.method,
            "method_params": dict(self.method_params),
            "provenance": self.provenance,
            "freeze_status": self.freeze_status,
            "intended_use": self.intended_use,
        }


@dataclass(frozen=True)
class FeatureRegistry:
    feature_version: str
    registry_status: str
    frozen_scope: tuple[str, ...]
    not_frozen_here: tuple[str, ...]
    policy: Mapping[str, Any]
    role_map: Mapping[str, Any]
    features: tuple[FeatureDefinition, ...]
    schema_sha256: str

    @property
    def feature_ids(self) -> tuple[str, ...]:
        return tuple(feature.feature_id for feature in self.features)

    def feature(self, feature_id: str) -> FeatureDefinition:
        for feature in self.features:
            if feature.feature_id == feature_id:
                return feature
        raise KeyError(f"feature {feature_id!r} is not registered")

    def features_by_family(self) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        for feature in self.features:
            grouped.setdefault(feature.family, []).append(feature.feature_id)
        return {family: tuple(ids) for family, ids in grouped.items()}

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": REGISTRY_SCHEMA,
            "feature_version": self.feature_version,
            "registry_status": self.registry_status,
            "frozen_scope": list(self.frozen_scope),
            "not_frozen_here": list(self.not_frozen_here),
            "policy": dict(self.policy),
            "role_map": dict(self.role_map),
            "features": [feature.to_dict() for feature in self.features],
        }


def _require(
    condition: bool, message: str
) -> None:
    if not condition:
        raise FeatureRegistryError(message)


def _require_text(value: Any, field: str, where: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{where}: {field} must be non-empty text")
    return value.strip()


def _require_optional_seconds(value: Any, field: str, where: str) -> float | None:
    if value is None:
        return None
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{where}: {field} must be a number or null",
    )
    numeric = float(value)
    _require(numeric >= 0, f"{where}: {field} must be >= 0")
    return numeric


def _parse_feature(payload: Any, index: int, chamber_roles: tuple[str, ...], hot_roles: tuple[str, ...]) -> FeatureDefinition:
    where = f"feature[{index}]"
    _require(isinstance(payload, Mapping), f"{where} must be a mapping")
    keys = set(payload)
    missing = _FEATURE_KEYS - keys
    extra = keys - _FEATURE_KEYS
    _require(not missing, f"{where}: missing keys {sorted(missing)}")
    _require(not extra, f"{where}: unknown keys {sorted(extra)}")

    feature_id = _require_text(payload["feature_id"], "feature_id", where)
    where = f"feature {feature_id!r}"
    family = _require_text(payload["family"], "family", where)
    _require(family in FAMILIES, f"{where}: unknown family {family!r}")
    method = _require_text(payload["method"], "method", where)
    _require(method in METHODS, f"{where}: unknown method {method!r}")
    _require(
        payload["dtype"] in ("float", "int"),
        f"{where}: dtype must be float or int",
    )
    _require_text(payload["unit"], "unit", where)
    _require_text(payload["version"], "version", where)
    _require_text(payload["physical_meaning"], "physical_meaning", where)
    _require_text(payload["source_schema"], "source_schema", where)
    _require_text(payload["quality_requirements"], "quality_requirements", where)
    _require_text(payload["missing_data_policy"], "missing_data_policy", where)
    _require_text(
        payload["first_valid_timestamp_rule"], "first_valid_timestamp_rule", where
    )
    _require_text(
        payload["causal_availability_condition"],
        "causal_availability_condition",
        where,
    )
    _require_text(payload["aggregation_definition"], "aggregation_definition", where)
    _require_text(payload["provenance"], "provenance", where)
    _require_text(payload["intended_use"], "intended_use", where)
    _require(
        payload["freeze_status"] == FROZEN_DEFINITION,
        f"{where}: freeze_status must be {FROZEN_DEFINITION}",
    )
    for field in ("source_fields", "sensor_roles"):
        value = payload[field]
        _require(
            isinstance(value, list) and value and all(isinstance(v, str) and v for v in value),
            f"{where}: {field} must be a non-empty string list",
        )
    params = payload["method_params"]
    _require(isinstance(params, Mapping), f"{where}: method_params must be a mapping")
    params = {str(key): str(value) for key, value in params.items()}

    lookback_s = _require_optional_seconds(payload["lookback_s"], "lookback_s", where)
    minimum_history_s = _require_optional_seconds(
        payload["minimum_history_s"], "minimum_history_s", where
    )
    _require(minimum_history_s is not None, f"{where}: minimum_history_s is required")
    max_gap_s = _require_optional_seconds(payload["max_gap_s"], "max_gap_s", where)

    roles = tuple(payload["sensor_roles"])
    if method == METHOD_INSTANTANEOUS_AGGREGATE:
        _require(
            params.get("statistic") in AGGREGATE_STATISTICS,
            f"{where}: aggregate statistic must be one of {AGGREGATE_STATISTICS}",
        )
        _require(
            set(roles) == set(chamber_roles),
            f"{where}: aggregate must use exactly the chamber-air roles",
        )
        _require(
            family == FAMILY_INSTANTANEOUS_THERMAL,
            f"{where}: aggregate family must be instantaneous_thermal",
        )
    elif method == METHOD_INSTANTANEOUS_PROBE:
        _require(len(roles) == 1, f"{where}: probe method requires exactly one role")
        _require(
            roles[0] in chamber_roles or roles[0] in hot_roles,
            f"{where}: unknown probe role {roles[0]!r}",
        )
        if roles[0] in hot_roles:
            _require(
                family == FAMILY_DIAGNOSTIC_THERMAL
                and "diagnostic" in payload["intended_use"],
                f"{where}: hot-side probe must be diagnostic-only",
            )
        else:
            _require(
                family == FAMILY_INSTANTANEOUS_THERMAL,
                f"{where}: chamber probe family must be instantaneous_thermal",
            )
    elif method == METHOD_ROLLING_THERMAL:
        _require(
            params.get("statistic") in ROLLING_STATISTICS,
            f"{where}: rolling statistic must be one of {ROLLING_STATISTICS}",
        )
        _require(
            set(roles) == set(chamber_roles),
            f"{where}: rolling thermal must use exactly the chamber-air roles",
        )
        _require(lookback_s is not None and lookback_s > 0, f"{where}: rolling lookback required")
        _require(
            minimum_history_s == lookback_s,
            f"{where}: rolling minimum history must equal the lookback",
        )
        _require(max_gap_s is not None and max_gap_s > 0, f"{where}: rolling max_gap_s required")
    elif method == METHOD_DOOR_OPEN:
        _require(family == FAMILY_DOOR, f"{where}: door method family mismatch")
    elif method == METHOD_DOOR_TIME_SINCE_OPEN:
        _require(family == FAMILY_DOOR, f"{where}: door method family mismatch")
    elif method == METHOD_DOOR_DURATION:
        _require(family == FAMILY_DOOR, f"{where}: door method family mismatch")
    elif method == METHOD_DOOR_COUNT:
        _require(family == FAMILY_DOOR, f"{where}: door method family mismatch")
        _require(lookback_s == 60.0, f"{where}: door count lookback must be 60 s")
    elif method == METHOD_ACTUATION_STATE:
        _require(
            params.get("channel") in ACTUATION_CHANNELS,
            f"{where}: actuation channel must be one of {ACTUATION_CHANNELS}",
        )
        _require(family == FAMILY_ACTUATION, f"{where}: actuation family mismatch")
    elif method == METHOD_ACTUATION_DUTY:
        _require(family == FAMILY_ACTUATION, f"{where}: actuation family mismatch")
    elif method == METHOD_ACTUATION_SINCE_CHANGE:
        _require(family == FAMILY_ACTUATION, f"{where}: actuation family mismatch")
    elif method == METHOD_ELECTRICAL_CHANNEL:
        _require(
            params.get("field") in ELECTRICAL_FIELDS,
            f"{where}: electrical field must be one of {ELECTRICAL_FIELDS}",
        )
        _require(family == FAMILY_ELECTRICAL, f"{where}: electrical family mismatch")
    elif method == METHOD_INTEGRATED_POWER:
        _require(
            params.get("window") == "since_boot_start",
            f"{where}: integrated power window must be since_boot_start",
        )
        _require(family == FAMILY_ELECTRICAL, f"{where}: electrical family mismatch")
    elif method == METHOD_ENVIRONMENT_CHANNEL:
        _require(
            params.get("field") in ENVIRONMENT_FIELDS,
            f"{where}: environment field must be one of {ENVIRONMENT_FIELDS}",
        )
        _require(family == FAMILY_ENVIRONMENTAL, f"{where}: environment family mismatch")

    return FeatureDefinition(
        feature_id=feature_id,
        feature_name=_require_text(payload["feature_name"], "feature_name", where),
        version=_require_text(payload["version"], "version", where),
        dtype=str(payload["dtype"]),
        unit=payload["unit"],
        family=family,
        physical_meaning=payload["physical_meaning"],
        source_fields=tuple(payload["source_fields"]),
        source_schema=payload["source_schema"],
        sensor_roles=roles,
        quality_requirements=payload["quality_requirements"],
        time_domain=_require_text(payload["time_domain"], "time_domain", where),
        lookback_rule=payload["lookback_rule"],
        lookback_s=lookback_s,
        minimum_history_s=float(minimum_history_s),
        max_gap_s=max_gap_s,
        missing_data_policy=payload["missing_data_policy"],
        first_valid_timestamp_rule=payload["first_valid_timestamp_rule"],
        causal_availability_condition=payload["causal_availability_condition"],
        aggregation_definition=payload["aggregation_definition"],
        method=method,
        method_params=params,
        provenance=payload["provenance"],
        freeze_status=payload["freeze_status"],
        intended_use=payload["intended_use"],
    )


def load_registry(path: str | Path | None = None) -> FeatureRegistry:
    """Load, validate and hash the registry. Raises on any contract drift."""
    registry_path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
    try:
        text = registry_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FeatureRegistryError(
            f"cannot read feature registry {registry_path}: {exc}"
        ) from exc
    try:
        payload = yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        raise FeatureRegistryError(f"feature registry is not valid YAML: {exc}") from exc
    _require(isinstance(payload, Mapping), "registry root must be a mapping")
    keys = set(payload)
    missing = _TOP_KEYS - keys
    extra = keys - _TOP_KEYS
    _require(not missing, f"registry: missing keys {sorted(missing)}")
    _require(not extra, f"registry: unknown keys {sorted(extra)}")
    _require(payload["schema"] == REGISTRY_SCHEMA, f"registry: schema must be {REGISTRY_SCHEMA}")
    policy = payload["policy"]
    _require(isinstance(policy, Mapping), "registry: policy must be a mapping")
    _require(
        set(policy) == _POLICY_KEYS,
        f"registry: policy keys mismatch {sorted(set(policy) ^ _POLICY_KEYS)}",
    )
    role_map = payload["role_map"]
    _require(isinstance(role_map, Mapping), "registry: role_map must be a mapping")
    chamber_roles = tuple(role_map.get("chamber_air_roles", ()))
    hot_roles = tuple(role_map.get("hot_side_roles", ()))
    _require(chamber_roles, "registry: chamber_air_roles must be non-empty")
    observed = role_map.get("observed_rig")
    _require(isinstance(observed, Mapping), "registry: observed_rig role map required")
    slots = observed.get("slots")
    _require(isinstance(slots, Mapping) and slots, "registry: observed_rig slots required")
    observed_chamber = {
        position
        for entry in slots.values()
        if isinstance(entry, Mapping) and entry.get("in_chamber_air_aggregate") is True
        for position in [entry.get("physical_position")]
    }
    _require(
        observed_chamber == set(chamber_roles),
        "registry: observed_rig chamber slots must match chamber_air_roles",
    )
    hot_positions = {
        entry.get("physical_position")
        for entry in slots.values()
        if isinstance(entry, Mapping) and entry.get("in_chamber_air_aggregate") is False
    }
    _require(
        set(hot_roles) <= hot_positions,
        "registry: hot_side_roles must be excluded from the chamber aggregate",
    )

    raw_features = payload["features"]
    _require(isinstance(raw_features, list) and raw_features, "registry: features required")
    features = tuple(
        _parse_feature(item, index, chamber_roles, hot_roles)
        for index, item in enumerate(raw_features, start=1)
    )
    ids = [feature.feature_id for feature in features]
    _require(len(ids) == len(set(ids)), "registry: duplicate feature_id")
    versions = {feature.version for feature in features}
    _require(len(versions) == 1, "registry: all features share one version")
    _require(
        set(feature.freeze_status for feature in features) == {FROZEN_DEFINITION},
        "registry: every feature definition must be frozen",
    )

    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return FeatureRegistry(
        feature_version=payload["feature_version"],
        registry_status=payload["registry_status"],
        frozen_scope=tuple(payload["frozen_scope"]),
        not_frozen_here=tuple(payload["not_frozen_here"]),
        policy=dict(policy),
        role_map=dict(role_map),
        features=features,
        schema_sha256=hashlib.sha256(canonical).hexdigest(),
    )
