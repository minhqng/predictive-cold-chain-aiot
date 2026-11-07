"""W10 feature registry freeze and validation tests (B-W10-01)."""

from __future__ import annotations

from pathlib import Path

import pytest

from coldguard_ml.feature_registry import (
    DEFAULT_REGISTRY_PATH,
    FROZEN_DEFINITION,
    FeatureRegistryError,
    load_registry,
)

EXPECTED_FEATURES = (
    "T_chamber_max_c",
    "T_chamber_min_c",
    "T_chamber_mean_c",
    "T_chamber_spread_c",
    "T_center_c",
    "T_bottom_c",
    "T_near_door_c",
    "T_tec_hot_side_c",
    "rolling_mean_temperature_60s",
    "rolling_std_temperature_60s",
    "rolling_min_temperature_60s",
    "rolling_max_temperature_60s",
    "past_only_slope_c_per_min_60s",
    "past_only_temperature_delta_60s",
    "past_only_spatial_spread_60s",
    "door_open",
    "time_since_open",
    "duration_so_far",
    "count_past_60s",
    "requested_cooling",
    "applied_cooling",
    "readback_cooling",
    "applied_duty",
    "time_since_confirmed_applied_change",
    "cooling_voltage_v",
    "cooling_current_a",
    "cooling_power_w",
    "energy_counter_wh",
    "past_integrated_cooling_energy_wh",
    "ambient_temperature_c",
    "relative_humidity_pct",
)


def test_registry_freezes_exact_feature_order():
    registry = load_registry()
    assert registry.feature_version == "CG-FEAT-1.0"
    assert registry.registry_status == "FROZEN_DEFINITIONS"
    assert registry.feature_ids == EXPECTED_FEATURES
    assert len(registry.features) == 31


def test_every_entry_carries_the_required_contract_fields():
    registry = load_registry()
    for feature in registry.features:
        assert feature.feature_name
        assert feature.version == "1.0"
        assert feature.dtype in ("float", "int")
        assert feature.unit
        assert feature.family
        assert feature.physical_meaning
        assert feature.source_fields
        assert feature.source_schema
        assert feature.sensor_roles
        assert feature.quality_requirements
        assert feature.time_domain == "source_declared"
        assert feature.lookback_rule
        assert feature.minimum_history_s >= 0
        assert feature.missing_data_policy
        assert feature.first_valid_timestamp_rule
        assert feature.causal_availability_condition
        assert feature.aggregation_definition
        assert feature.provenance
        assert feature.freeze_status == FROZEN_DEFINITION
        assert feature.intended_use


def test_hot_side_role_is_excluded_from_chamber_aggregates():
    registry = load_registry()
    chamber_roles = set(registry.role_map["chamber_air_roles"])
    hot_roles = set(registry.role_map["hot_side_roles"])
    assert "TEC_HOT_SIDE" in hot_roles
    assert "TEC_HOT_SIDE" not in chamber_roles
    for feature in registry.features:
        if feature.method == "instantaneous_aggregate":
            assert set(feature.sensor_roles) == chamber_roles
        if feature.method == "rolling_thermal":
            assert set(feature.sensor_roles) == chamber_roles
    hot = registry.feature("T_tec_hot_side_c")
    assert hot.family == "diagnostic_thermal"
    assert "diagnostic" in hot.intended_use
    assert hot.sensor_roles == ("TEC_HOT_SIDE",)


def test_rolling_features_declare_lookback_history_and_gap_semantics():
    registry = load_registry()
    for feature in registry.features:
        if feature.method != "rolling_thermal":
            continue
        assert feature.lookback_s == 60.0
        assert feature.minimum_history_s == 60.0
        assert feature.max_gap_s == 5.0
        assert "(t - 60 s, t]" in feature.lookback_rule
        assert "missing" in feature.missing_data_policy.lower()


def test_registry_hash_is_stable_across_loads():
    first = load_registry()
    second = load_registry()
    assert first.schema_sha256 == second.schema_sha256
    assert len(first.schema_sha256) == 64


def test_definition_change_changes_the_registry_hash(tmp_path: Path):
    text = DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8")
    modified = text.replace(
        "statistic: time_weighted_mean", "statistic: min", 1
    )
    assert modified != text
    target = tmp_path / "feature-registry-v1.yaml"
    target.write_text(modified, encoding="utf-8")
    changed = load_registry(target)
    assert changed.schema_sha256 != load_registry().schema_sha256


def test_feature_order_change_changes_the_registry_hash(tmp_path: Path):
    text = DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8")
    first = text.index("  - feature_id: T_chamber_max_c")
    second = text.index("  - feature_id: T_chamber_min_c")
    third = text.index("  - feature_id: T_chamber_mean_c")
    block_a = text[first:second]
    block_b = text[second:third]
    modified = text[:first] + block_b + block_a + text[third:]
    target = tmp_path / "feature-registry-v1.yaml"
    target.write_text(modified, encoding="utf-8")
    changed = load_registry(target)
    assert changed.feature_ids[:3] == (
        "T_chamber_min_c",
        "T_chamber_max_c",
        "T_chamber_mean_c",
    )
    assert changed.schema_sha256 != load_registry().schema_sha256


def test_duplicate_yaml_keys_are_refused(tmp_path: Path):
    text = DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8")
    target = tmp_path / "feature-registry-v1.yaml"
    target.write_text(text + "schema: duplicate\n", encoding="utf-8")
    with pytest.raises(FeatureRegistryError, match="duplicate registry key"):
        load_registry(target)


def test_unknown_feature_key_is_refused(tmp_path: Path):
    text = DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8")
    modified = text.replace(
        "    intended_use: model_input_candidate",
        "    intended_use: model_input_candidate\n    invented_field: true",
        1,
    )
    target = tmp_path / "feature-registry-v1.yaml"
    target.write_text(modified, encoding="utf-8")
    with pytest.raises(FeatureRegistryError, match="unknown keys"):
        load_registry(target)


def test_unfrozen_physical_parameters_are_not_claimed():
    registry = load_registry()
    assert "T_critical_c" in registry.not_frozen_here
    assert "primary_horizon_H" in registry.not_frozen_here
    assert "representative_temperature_for_final_labels" in registry.not_frozen_here
    assert "primary_horizon_H" not in registry.frozen_scope


def test_features_by_family_cover_all_required_families():
    registry = load_registry()
    families = registry.features_by_family()
    assert set(families) == {
        "instantaneous_thermal",
        "diagnostic_thermal",
        "rolling_thermal",
        "door_context",
        "actuation_context",
        "electrical_context",
        "environmental_context",
    }
    assert len(families["door_context"]) == 4
    assert len(families["actuation_context"]) == 5
