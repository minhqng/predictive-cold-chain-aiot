"""Leader-owned tests for the live inference bridge (fail-closed contracts).

Sensor-frame fixtures reuse Member A's committed capture line
(evidence/A/HANDOFF/member-a-bcd-contract.json) so producer parsing stays
bound to the delivered device schema. No member file is modified.
"""

import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

WORKTREE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / "backend"))

from integration.leader_live_inference import (  # noqa: E402
    FEATURES, FeatureIncomplete, Row, canonical_feature_schema, compute_features,
    live_prediction, load_demo_model, load_demo_regressor, load_w15_model,
    model_contract, model_metadata, row_from_mapping, score_or_block,
)
from coldguard_backend.inference import InferenceUnavailable  # noqa: E402
import integration.leader_live_inference as inference_module  # noqa: E402


CONTRACT = WORKTREE / "evidence" / "A" / "HANDOFF" / "member-a-bcd-contract.json"


def committed_frame() -> str:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))["probe_frame"]["committed_capture_line"]


def ts(offset_s: float) -> datetime:
    return datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_s)


def live_shape_row(offset_s: float, **overrides) -> Row:
    """Rows matching the current cg-w06 rig: t1/t3 chamber probes, no t4 column,
    BME t_air+rh degraded right now, door UNKNOWN, PZEM electrical INVALID."""
    base = dict(
        received_at=ts(offset_s), boot_id="b1", t1_c=20.0, t3_c=19.0, t4_c=None,
        t_air_c=28.0, rh_pct=55.0, door_state="UNKNOWN", thermal_valid=True,
        environment_valid=True, electrical_valid=False, applied_cooling="OFF",
        applied_duty=0.0, cooling_voltage_v=None, cooling_current_a=None,
        cooling_power_w=None, energy_counter_wh=None,
    )
    base.update(overrides)
    return Row(**base)


EXPECTED_MISSING_NOW = sorted(
    set(FEATURES) - {
        "T_center_c", "T_bottom_c", "count_past_60s", "applied_cooling",
        "applied_duty", "ambient_temperature_c", "relative_humidity_pct",
    }
)


def test_t4_mapping_is_rom_authority_bound():
    m = {
        "backend_received_at": ts(0), "boot_id": "b1",
        "t1_c": 25.0625, "t3_c": 25.0625, "t4_c": None,
        "thermal_quality": "VALID", "raw_frame": committed_frame(),
    }
    row = row_from_mapping(m)
    assert row.t4_c == pytest.approx(25.0625)

    tampered = committed_frame().replace("spare_rom=283BE5C9000000A9", "spare_rom=28112233000000AA")
    row_bad = row_from_mapping({**m, "raw_frame": tampered})
    assert row_bad.t4_c is None


def test_real_rig_shape_fails_closed_with_exact_missing_set():
    rows = [live_shape_row(k) for k in range(0, 92)]
    features = compute_features(rows)
    missing = sorted(fid for fid in FEATURES if features[fid] is None)
    assert missing == EXPECTED_MISSING_NOW
    raise_missing = FeatureIncomplete(missing)
    assert raise_missing.missing == EXPECTED_MISSING_NOW


def test_full_chamber_rows_compute_rolls_from_t4_source():
    # All three chamber roles producing, t4 arriving spare-slot style is covered
    # by test_t4_mapping_is_rom_authority_bound; here the Row-level math.
    rows = [live_shape_row(k, t4_c=18.0) for k in range(0, 93)]
    f = compute_features(rows)
    assert f["T_center_c"] == pytest.approx(20.0)
    assert f["T_bottom_c"] == pytest.approx(19.0)
    assert f["T_near_door_c"] == pytest.approx(18.0)
    assert f["T_chamber_mean_c"] == pytest.approx((20.0 + 19.0 + 18.0) / 3)
    assert f["T_chamber_spread_c"] == pytest.approx(2.0)
    assert f["rolling_mean_temperature_60s"] == pytest.approx(f["T_chamber_mean_c"])
    assert f["rolling_std_temperature_60s"] == pytest.approx(0.0)
    assert f["rolling_min_temperature_60s"] == pytest.approx(f["T_chamber_mean_c"])
    assert f["rolling_max_temperature_60s"] == pytest.approx(f["T_chamber_mean_c"])
    assert f["past_only_temperature_delta_60s"] == pytest.approx(0.0)
    assert f["past_only_slope_c_per_min_60s"] == pytest.approx(0.0)
    assert f["past_only_spatial_spread_60s"] == pytest.approx(2.0)


def test_slope_detects_warming():
    # Only t1 ramps (+1 c/min); the chamber mean = (t1 + t3 + t4) / 3 therefore
    # ramps at exactly 1/3 c/min over the covered 59 s window (k = 33..92).
    rows = [live_shape_row(k, t1_c=19.0 + k / 60.0, t3_c=19.0, t4_c=19.0) for k in range(0, 93)]
    f = compute_features(rows)
    assert f["past_only_slope_c_per_min_60s"] == pytest.approx(1.0 / 3.0, abs=1e-6)
    assert f["past_only_temperature_delta_60s"] == pytest.approx((59.0 / 60.0) / 3.0, abs=1e-6)


def test_gap_over_max_breaks_rolling_window():
    rows = [live_shape_row(k) for k in range(0, 62)]
    rows += [live_shape_row(70.0)]  # 8 s gap above max_gap_s = 5
    f = compute_features(rows)
    assert f["rolling_mean_temperature_60s"] is None


def door_row(offset_s: float, state: str, raw: int, **overrides) -> Row:
    """Unit fixture only: a row whose original-frame door fields attest a boot."""
    base = dict(
        door_state=state, door_raw=raw, door_status="OK", door_quality="VALID",
        door_transitions=1, door_open_firmware=1.0 if state == "OPEN" else 0.0,
    )
    base.update(overrides)
    return live_shape_row(offset_s, **base)


def test_door_trust_rules_honored():
    rows = [door_row(0.0, "CLOSED", 0)]
    rows += [door_row(30.0, "OPEN", 1)]
    rows += [door_row(31.0, "OPEN", 1)]
    rows += [door_row(45.0, "CLOSED", 0)]
    rows += [door_row(60.0, "CLOSED", 0)]
    f = compute_features(rows)
    assert f["door_open"] == 0.0
    assert f["time_since_open"] == pytest.approx(30.0)
    assert f["duration_so_far"] == 0.0
    assert f["count_past_60s"] == 1.0
    f2 = compute_features([live_shape_row(0.0, door_state="UNKNOWN")])
    assert f2["door_open"] is None
    assert f2["duration_so_far"] is None
    assert f2["time_since_open"] is None


def test_door_requires_same_boot_attestation():
    # Only raw=1 appears and the device never reported a transition: the lone
    # level is not a polarity attestation, so no door state is trusted.
    rows = [door_row(0.0, "OPEN", 1, door_transitions=0)]
    f = compute_features(rows)
    assert f["door_open"] is None
    assert f["time_since_open"] is None
    assert f["duration_so_far"] is None


def test_door_quality_gate_fails_closed():
    # The anchor itself reports door_quality=UNKNOWN: its state is not trusted
    # even though the boot has an attested edge.
    rows = [door_row(0.0, "CLOSED", 0),
            door_row(1.0, "OPEN", 1, door_quality="UNKNOWN")]
    f = compute_features(rows)
    assert f["door_open"] is None
    assert f["duration_so_far"] is None


def test_door_firmware_mapping_conflict_refused():
    # Both raw levels appear (attested) but the device's door_open is inverted
    # for raw=0; the delivered mapping conflict suspends all door features.
    rows = [door_row(0.0, "CLOSED", 0, door_open_firmware=1.0),
            door_row(1.0, "OPEN", 1, door_open_firmware=1.0)]
    f = compute_features(rows)
    assert f["door_open"] is None
    assert f["time_since_open"] is None


def test_lifetime_open_edge_outside_60s_tail_is_retained():
    # The only opening edge is at t=10 s; the anchor is at 260 s. A 240-row
    # tail would lose it, which is exactly the pre-fix missing-feature cause.
    rows = [door_row(0.0, "CLOSED", 0), door_row(10.0, "OPEN", 1),
            door_row(11.0, "CLOSED", 0)]
    rows += [door_row(t, "CLOSED", 0) for t in range(200, 261)]
    f = compute_features(rows)
    assert f["door_open"] == 0.0
    assert f["time_since_open"] == pytest.approx(250.0)
    assert f["duration_so_far"] == 0.0
    assert f["count_past_60s"] == 0.0


def test_applied_change_outside_60s_tail_is_retained():
    rows = [live_shape_row(0.0, applied_cooling="OFF", applied_duty=0.0),
            live_shape_row(10.0, applied_cooling="ON", applied_duty=0.2),
            live_shape_row(20.0, applied_cooling="OFF", applied_duty=0.0)]
    rows += [live_shape_row(t, applied_cooling="OFF", applied_duty=0.0)
             for t in range(200, 261)]
    f = compute_features(rows)
    assert f["time_since_confirmed_applied_change"] == pytest.approx(240.0)


def test_energy_counter_reset_is_refused():
    def row(t, wh):
        return live_shape_row(t, electrical_valid=True, cooling_voltage_v=11.9,
                              cooling_current_a=0.1, cooling_power_w=1.0,
                              energy_counter_wh=wh)
    f = compute_features([row(0, 10.0), row(1, 11.0), row(2, 10.0)])
    assert f["energy_counter_wh"] is None


def test_integrated_energy_refuses_invalid_interval():
    valid = live_shape_row(0.0, electrical_valid=True, cooling_voltage_v=11.9,
                           cooling_current_a=0.1, cooling_power_w=1.0,
                           energy_counter_wh=10.0)
    invalid = live_shape_row(1.0, electrical_valid=False)
    anchor = live_shape_row(2.0, electrical_valid=True, cooling_voltage_v=11.9,
                            cooling_current_a=0.1, cooling_power_w=1.0,
                            energy_counter_wh=10.0)
    f = compute_features([valid, invalid, anchor])
    assert f["past_integrated_cooling_energy_wh"] is None


def test_electrical_zero_never_promoted():
    rows = [live_shape_row(k, cooling_voltage_v=0.0, cooling_current_a=0.0,
                           cooling_power_w=0.0, energy_counter_wh=0.0,
                           electrical_valid=True)
            for k in range(0, 93)]
    f = compute_features(rows)
    assert f["cooling_voltage_v"] == 0.0  # VALID quality: an honest 0.0 W idle
    assert f["past_integrated_cooling_energy_wh"] == pytest.approx(0.0)
    f2 = compute_features([live_shape_row(0.0, cooling_voltage_v=0.0)])
    assert f2["cooling_voltage_v"] is None  # INVALID quality stays missing


def test_applied_change_semantics():
    rows = [live_shape_row(k) for k in range(0, 60)]
    rows += [live_shape_row(60.0, applied_cooling="ON", applied_duty=0.5)]
    rows += [live_shape_row(75.0, applied_cooling="ON", applied_duty=0.5)]
    f = compute_features(rows)
    assert f["applied_cooling"] == 1.0
    assert f["applied_duty"] == 0.5
    assert f["time_since_confirmed_applied_change"] == pytest.approx(15.0)
    f2 = compute_features(rows[:60])
    assert f2["time_since_confirmed_applied_change"] is None


def test_environment_missing_when_degraded():
    rows = [live_shape_row(0.0, t_air_c=None, rh_pct=None, environment_valid=False)]
    f = compute_features(rows)
    assert f["ambient_temperature_c"] is None
    assert f["relative_humidity_pct"] is None


def test_canonical_schema_binds_to_delivered_manifest():
    manifest = json.loads(
        (WORKTREE / "ml" / "reports" / "W15" / "model" / "model-manifest-W15.json")
        .read_text(encoding="utf-8")
    )
    _path, sha, _fv = canonical_feature_schema()
    assert sha == manifest["feature_schema_hash"]


def test_real_w15_artifact_scores_mechanically():
    """Artifact mechanism check, NOT real-data inference: a complete legal
    numeric vector yields one finite risk in [0,1] from the frozen ubj."""
    model = load_w15_model("coldguard-w15-synthetic-xgb-candidate-v1")
    risk = model.score({fid: 0.5 for fid in FEATURES})
    assert math.isfinite(risk)
    assert 0.0 <= risk <= 1.0


def test_score_or_block_uses_manifest_order_and_is_deterministic():
    model = load_w15_model("coldguard-w15-synthetic-xgb-candidate-v1")
    features = {fid: 0.5 for fid in FEATURES}
    first = score_or_block(model, features)
    second = score_or_block(model, features)
    assert first == second
    assert first["feature_count"] == len(FEATURES)
    assert math.isfinite(first["risk"]) and 0.0 <= first["risk"] <= 1.0


def test_legacy_model_metadata_is_truthful():
    meta = model_metadata()
    assert meta["model_selection"] == "legacy_default"
    assert meta["training_class"] == "SYNTHETIC"
    assert meta["training_data_class"] == "SYNTHETIC_SOFTWARE_CONTROL_ONLY"
    assert meta["release_eligibility"] == "NON_DEPLOYABLE_CANDIDATE"
    assert meta["feature_total"] == 28
    assert meta["demo_only"] is True
    assert any("not persisted" in note for note in meta["notes"])


def complete_unit_row(t: float) -> Row:
    """Complete UNIT FIXTURE (not field data): exercises the whole score path."""
    door_open = 10.0 <= t < 20.0
    return live_shape_row(
        t, t4_c=18.0,
        electrical_valid=True, cooling_voltage_v=11.9, cooling_current_a=0.1,
        cooling_power_w=1.0, energy_counter_wh=10.0 + t * 0.001,
        applied_cooling="ON" if 30.0 <= t < 40.0 else "OFF",
        applied_duty=0.2 if 30.0 <= t < 40.0 else 0.0,
        door_state="OPEN" if door_open else "CLOSED",
        door_raw=1 if door_open else 0, door_status="OK",
        door_quality="VALID", door_transitions=2,
        door_open_firmware=1.0 if door_open else 0.0,
    )


def test_complete_unit_fixture_scores_through_real_artifact():
    """UNIT FIXTURE ONLY: no field-data claim. Proves the success path loads
    the frozen artifact and returns a finite score in [0,1]."""
    rows = [complete_unit_row(float(t)) for t in range(0, 90)]
    payload = live_prediction(
        "coldguard-001", rows=rows, now=rows[-1].received_at,
        source="UNIT_FIXTURE")
    assert payload["score_status"] == "OK_DEMO_ONLY"
    assert payload["missing_features"] == []
    assert payload["feature_count"] == payload["feature_total"] == 28
    assert math.isfinite(payload["score"]) and 0.0 <= payload["score"] <= 1.0
    assert payload["source"] == "UNIT_FIXTURE"
    assert payload["training_class"] == "SYNTHETIC"


def test_live_prediction_reports_database_block(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise InferenceUnavailable("database unreachable")
    monkeypatch.setattr(inference_module, "fetch_current_boot_rows", unavailable)
    payload = live_prediction("coldguard-001")
    assert payload["score_status"] == "BLOCKED_DATABASE_UNAVAILABLE"
    assert payload["score"] is None
    assert payload["source"] == "REAL_SERIAL_UNAVAILABLE"


def test_live_prediction_blocks_missing_features_without_scoring():
    rows = [live_shape_row(k) for k in range(0, 93)]
    payload = live_prediction(
        "coldguard-001", rows=rows, now=rows[-1].received_at,
        source="UNIT_FIXTURE")
    assert payload["score_status"] == "BLOCKED_FEATURES_INCOMPLETE"
    assert payload["score"] is None
    assert "T_near_door_c" in payload["missing_features"]
    assert payload["source"] == "UNIT_FIXTURE"


def test_live_prediction_marks_stale_anchor_and_withholds_score():
    rows = [live_shape_row(k) for k in range(0, 93)]
    payload = live_prediction(
        "coldguard-001", rows=rows,
        now=rows[-1].received_at + timedelta(seconds=20),
        source="UNIT_FIXTURE")
    assert payload["score_status"] == "STALE_NO_SCORE"
    assert payload["score"] is None
    assert payload["fresh"] is False


def _selected_model_dir(
    tmp_path: Path, names: list[str], *, schema_sha: str | None = None,
    **manifest_extra,
) -> Path:
    source = WORKTREE / "ml" / "reports" / "W15" / "model" / "model.ubj"
    artifact = tmp_path / "model.ubj"
    artifact.write_bytes(source.read_bytes())
    schema = tmp_path / "feature-schema.json"
    schema.write_text(json.dumps(names), encoding="utf-8")
    manifest = {
        "model_version": "leader-real-xgb-demo-test",
        "feature_version": "CG-FEAT-DEMO-SUBSET-1.0",
        "model_artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "feature_schema_hash": schema_sha or hashlib.sha256(schema.read_bytes()).hexdigest(),
        "ordered_feature_ids": names,
        "horizon_s": 60,
        "training_data_class": "REAL_PHYSICAL",
        "release_eligibility": "EXPERIMENTAL_DEMO",
        "target": "chamber_overheat_60s",
        "horizon_status": "DEMO",
        "model_library_version": "3.4.1",
    }
    manifest.update(manifest_extra)
    (tmp_path / "model-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


TEMP_FEATURES = [
    "T_chamber_mean_c", "T_chamber_max_c", "T_chamber_min_c",
    "T_chamber_spread_c", "T_center_c", "T_bottom_c", "T_near_door_c",
    "rolling_mean_temperature_60s", "rolling_std_temperature_60s",
    "rolling_min_temperature_60s", "rolling_max_temperature_60s",
    "past_only_slope_c_per_min_60s", "past_only_temperature_delta_60s",
    "past_only_spatial_spread_60s", "cooling_voltage_v", "cooling_current_a",
]
TEMP_MANIFEST = {
    "model_task": "temperature_forecast",
    "objective": "reg:squarederror",
    "target_transform": "delta_from_current_chamber_mean",
    "baseline_feature_id": "T_chamber_mean_c",
    "raw_native_load_prohibited": False,
    "release_eligibility": "EXPERIMENTAL_DEMO_ONLY",
}


def test_selected_model_dir_reads_subset_contract_and_dynamic_labels(tmp_path):
    names = ["T_chamber_mean_c", "time_since_open", "ambient_temperature_c"]
    directory = _selected_model_dir(tmp_path, names)
    contract = model_contract(directory)
    assert contract.feature_names == tuple(names)
    assert contract.training_class == "REAL_PHYSICAL"
    assert contract.release_eligibility == "EXPERIMENTAL_DEMO"
    assert contract.is_legacy is False
    meta = model_metadata(directory)
    assert meta["feature_total"] == 3
    assert meta["model_selection"] == "explicit_model_dir"
    assert meta["training_class"] == "REAL_PHYSICAL"


def test_selected_model_dir_loads_through_frozen_loader(tmp_path):
    # Same real artifact bytes, new manifest/schema selection path. This is a
    # loader-mechanism check, not real-data inference.
    names = list(FEATURES)
    directory = _selected_model_dir(tmp_path, names)
    model = load_demo_model("leader-real-xgb-demo-test", directory)
    assert model.spec.model_version == "leader-real-xgb-demo-test"
    assert tuple(model.spec.feature_names) == tuple(names)
    risk = model.score({fid: 0.5 for fid in names})
    assert math.isfinite(risk) and 0.0 <= risk <= 1.0


def test_temp_forecast_contract_and_metadata(tmp_path):
    directory = _selected_model_dir(tmp_path, TEMP_FEATURES, **TEMP_MANIFEST)
    contract = model_contract(directory)
    assert contract.model_task == "temperature_forecast"
    assert contract.objective == "reg:squarederror"
    assert contract.target_transform == "delta_from_current_chamber_mean"
    assert contract.baseline_feature_id == "T_chamber_mean_c"
    assert contract.raw_native_load_prohibited is False
    assert contract.feature_names == tuple(TEMP_FEATURES)
    meta = model_metadata(directory)
    assert meta["model_task"] == "temperature_forecast"
    assert meta["unit"] == "degC"
    assert meta["feature_total"] == 16
    assert meta["training_class"] == "REAL_PHYSICAL"
    assert meta["release_eligibility"] == "EXPERIMENTAL_DEMO_ONLY"


def test_temp_forecast_contract_requires_baseline_in_features(tmp_path):
    names = [fid for fid in TEMP_FEATURES if fid != "T_chamber_mean_c"]
    directory = _selected_model_dir(tmp_path, names, **TEMP_MANIFEST)
    with pytest.raises(InferenceUnavailable):
        model_contract(directory)


def test_temp_forecast_is_not_routed_through_risk_loader(tmp_path):
    directory = _selected_model_dir(tmp_path, TEMP_FEATURES, **TEMP_MANIFEST)
    with pytest.raises(InferenceUnavailable):
        load_demo_model("leader-real-xgb-demo-test", directory)


def test_regressor_rejects_classifier_objective(tmp_path):
    # Full 28-feature copy so the count check passes and the objective check
    # is the one that refuses the legacy binary:logistic artifact.
    directory = _selected_model_dir(tmp_path, list(FEATURES), **TEMP_MANIFEST)
    with pytest.raises(InferenceUnavailable):
        load_demo_regressor(directory)


def test_temp_forecast_live_prediction_plumbing(tmp_path, monkeypatch):
    """UNIT FIXTURE ONLY: verifies the °C delta path bypasses the legacy
    0..1 risk validator. The delta is injected; no real forecast is claimed."""
    directory = _selected_model_dir(tmp_path, TEMP_FEATURES, **TEMP_MANIFEST)

    class FakeRegressor:
        def predict(self, _features):
            return 0.5

    monkeypatch.setattr(
        inference_module, "_cached_regressor",
        lambda _contract, _version: FakeRegressor())
    rows = [complete_unit_row(float(t)) for t in range(0, 90)]
    payload = live_prediction(
        "coldguard-001", model_dir=directory, rows=rows,
        now=rows[-1].received_at, source="UNIT_FIXTURE")
    assert payload["model_task"] == "temperature_forecast"
    assert payload["forecast_status"] == "OK_EXPERIMENTAL_DEMO"
    assert payload["score"] is None
    assert payload["predicted_delta_c"] == pytest.approx(0.5)
    assert payload["predicted_temperature_c"] == pytest.approx(
        payload["current_chamber_mean_c"] + 0.5)
    assert payload["unit"] == "degC"
    assert payload["horizon_s"] == 60
    assert payload["training_class"] == "REAL_PHYSICAL"
    assert payload["release_eligibility"] == "EXPERIMENTAL_DEMO_ONLY"


def test_temp_forecast_stale_withholds_forecast(tmp_path, monkeypatch):
    directory = _selected_model_dir(tmp_path, TEMP_FEATURES, **TEMP_MANIFEST)
    monkeypatch.setattr(
        inference_module, "_cached_regressor",
        lambda _contract, _version: type("R", (), {"predict": lambda self, _f: 0.5})())
    rows = [complete_unit_row(float(t)) for t in range(0, 90)]
    payload = live_prediction(
        "coldguard-001", model_dir=directory, rows=rows,
        now=rows[-1].received_at + timedelta(seconds=20),
        source="UNIT_FIXTURE")
    assert payload["forecast_status"] == "STALE_NO_FORECAST"
    assert payload["predicted_temperature_c"] is None


NEW_TEMP_MODEL = Path(
    r"C:\cgb\xgb-train-20261113\ml\reports\leader-real-temp60-xgb-demo-20261113\model")


@pytest.mark.skipif(not (NEW_TEMP_MODEL / "model.ubj").exists(),
                    reason="new real temperature regressor not produced yet")
def test_new_temp_regressor_artifact_if_available():
    regressor = load_demo_regressor(NEW_TEMP_MODEL)
    assert regressor.contract.model_task == "temperature_forecast"
    assert regressor.contract.objective == "reg:squarederror"
    delta = regressor.predict({fid: 0.5 for fid in regressor.contract.feature_names})
    assert math.isfinite(delta)


def test_selected_model_dir_rejects_unimplemented_feature(tmp_path):
    directory = _selected_model_dir(tmp_path, ["T_chamber_mean_c", "not_a_real_feature"])
    with pytest.raises(InferenceUnavailable):
        model_contract(directory)


def test_selected_model_dir_rejects_schema_hash_mismatch(tmp_path):
    directory = _selected_model_dir(
        tmp_path, ["T_chamber_mean_c"], schema_sha="0" * 64)
    with pytest.raises(InferenceUnavailable):
        model_contract(directory)
