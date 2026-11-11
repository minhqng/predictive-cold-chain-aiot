"""Paths 2-4 (C→B, B→D, A→D) over committed evidence.

These paths need Member B's ``coldguard_ml`` dependency set
(numpy/pandas/scikit-learn/pyyaml). Without them the module skips honestly
(SKIP_INFRASTRUCTURE at module level) instead of failing collection:

    uv run --frozen --extra test --with-editable ../ml python -m pytest tests
"""

import json
import pathlib
import sys
from datetime import datetime, timezone

import pytest


def _setup_paths() -> pathlib.Path:
    root = pathlib.Path(__file__).resolve().parents[2]
    for candidate in (root, root / "ml" / "src", root / "control" / "src"):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    return root


ROOT_PATH = _setup_paths()

# Honest module-level skip when Member B's dependency set is absent.
try:
    import coldguard_ml  # noqa: F401, E402

    _ML_AVAILABLE = True
except ModuleNotFoundError:
    _ML_AVAILABLE = False

if not _ML_AVAILABLE:
    pytest.skip(
        "requires Member B's ml package dependencies: run backend tests with "
        "`uv run --frozen --extra test --with-editable ../ml`",
        allow_module_level=True,
    )

from coldguard_backend.cross_team_paths import (  # noqa: E402
    W13_HORIZONS_S,
    admit_rows,
    door_critical_sidecar_to_policy_views,
    label_records_to_prediction_view,
    labels_at_horizons,
    normalized_row_to_observation,
)

from coldguard_control.config import PolicyConfig  # noqa: E402
from coldguard_control.policy import (  # noqa: E402
    PolicyInput,
    PredictionView,
    RemotePathView,
    ThermalView,
    evaluate_policy,
)
from coldguard_control.types import (  # noqa: E402
    CoolingState,
    DeviceMode,
    ModelHealth,
    PolicyState,
    QualityState,
)

W10_RUN_CSV = (
    ROOT_PATH / "evidence" / "A" / "SOURCES" / "20261107" / "datasets"
    / "datasets" / "W10-02-normalized.csv"
)
W13_SIDECAR = ROOT_PATH / "evidence" / "A" / "W13" / "door-critical-input-20261109.json"
S1_600S = (
    ROOT_PATH / "evidence" / "A" / "W09" / "exports" / "CG-S1-H8C-600S.json"
)


def _w10_02_rows() -> list[dict]:
    """Map A's committed normalized export onto C's normalized row shape.

    W10-02 is a DATASET_ACCEPTED_S2 run whose declared timebase is HOST_STAMP
    (run_index.csv, device_timestamp_utc_source=DEVICE_HAS_NO_WALL_CLOCK):
    the host stamps are the dataset's owned event-time axis, carried as
    provenance — not inferred from seq.
    """
    import csv

    out = []
    with W10_RUN_CSV.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            time = datetime.fromisoformat(r["host_time_utc"])
            pwm = r["pwm_applied_permille"]
            out.append({
                "seq": int(r["seq"]),
                "run_id": r["run_tag"],
                "device_id": "coldguard-001",
                "boot_id": r["boot_id"],
                "time": time,
                "uptime_ms": int(float(r["uptime_ms"])),
                "t1_c": r["t1_c"], "t2_c": r["t2_c"], "t3_c": r["t3_c"],
                "t_air_c": r["air_c_reported"], "rh_pct": r["rh_pct"],
                "door_open": r["door_open"], "door_status": r["door_status"],
                "thermal_quality": r["quality"] if r["t1_status"] == "OK" else "INVALID",
                "environment_quality": "INVALID",
                "electrical_quality": "VALID" if r["current_status"] == "OK" else "INVALID",
                "overall_quality": r["quality"],
                "device_mode": r["state"] or None,
                "applied_cooling": r["tec_state"],
                "applied_duty": (float(pwm) / 1000.0) if pwm else None,
                "cooling_voltage_v": r["voltage_v"],
                "cooling_current_a": r["current_a"],
                "cooling_power_w": r["power_w"],
                "cooling_energy_counter_wh": r["energy_wh"],
                "hardware_config_id": r["hardware_config_id"],
                "firmware_version": r["firmware_version"],
                "calibration_id": None,
            })
    return out


def test_path2_committed_accepted_s2_run_admits_into_b_contract():
    rows = _w10_02_rows()
    assert len(rows) == 120
    report = admit_rows(rows, time_source="HOST_STAMP")
    assert report["refused"] == []
    assert report["deduplicated_count"] == 120
    observations = report["admitted"]
    doors = {o.door_state for o in observations}
    assert "OPEN" in doors and "CLOSED" in doors  # the real S2 disturbance
    assert all(o.run_id == "W10-02" for o in observations)
    assert all(o.time.tzinfo is not None for o in observations)
    # INVALID overall quality is a legal B vocabulary value and is preserved,
    # so dataset-level usability is never upgraded by the adapter.
    assert {o.overall_quality for o in observations} == {"INVALID"}
    from coldguard_ml.observations import rows_by_run
    runs = rows_by_run(observations)
    assert list(runs) == ["W10-02"]


def test_path2_clockless_identityless_encoding_is_refused_not_repaired():
    data = json.loads(S1_600S.read_text(encoding="utf-8"))
    assert data["frames"]["rows"] == 957
    # The committed S1 600s export: no valid rows, no event times, no device id.
    assert data["frames"]["reason"]
    with pytest.raises(Exception, match="NO_EVENT_TIME"):
        normalized_row_to_observation({
            "seq": 1, "device_id": "coldguard-001", "boot_id": "56044b74",
            "time": None, "run_id": "CG-S1-H8C-600S",
            "overall_quality": "INVALID", "applied_cooling": "OFF",
            "hardware_config_id": "CG-HW-001", "firmware_version": "fw",
        })
    with pytest.raises(Exception, match="NO_DEVICE_IDENTITY"):
        normalized_row_to_observation({
            "seq": 1, "device_id": "NOT_CARRIED_BY_THIS_ENCODING",
            "boot_id": "56044b74",
            "time": datetime(2026, 11, 7, 8, 16, 52, tzinfo=timezone.utc),
            "run_id": "CG-S1-H8C-600S", "overall_quality": "UNKNOWN",
            "applied_cooling": "OFF",
            "hardware_config_id": "CG-HW-001", "firmware_version": "fw",
        })


def test_path3_w13_horizon_set_evaluates_on_committed_run():
    rows = _w10_02_rows()
    admitted = admit_rows(rows)["admitted"]
    events = [(o.time, o) for o in admitted if o.door_state == "OPEN"]
    assert events, "the committed S2 run carries no door-open rows"
    from coldguard_ml.labels import CriticalEvent, CriticalEventSeries

    # The committed W10 semantics: door transitions are REPORTED_BY_FRAME_ONLY,
    # i.e. present but physically unattested -> trusted=False, never ground truth.
    series = CriticalEventSeries(
        run_id="W10-02",
        events=tuple(
            CriticalEvent(time=t, trusted=False, ref=f"{o.boot_id}:{o.seq}")
            for t, o in events
        ),
        series_id="committed-w10-02-door-unattested",
        coverage_end=admitted[-1].time,
    )
    anchors = [
        (
            admitted[0].time,
            (admitted[0].device_id, admitted[0].boot_id, admitted[0].seq),
        )
    ]
    report = labels_at_horizons(anchors, series)
    assert sorted(report) == sorted(W13_HORIZONS_S) == [30.0, 60.0, 120.0, 300.0]
    for horizon, records in report.items():
        for record in records:
            # An unattested door event is never silently promoted to a positive
            # critical-event label: beyond coverage the horizon is CENSORED,
            # not a negative; untrusted info never silently applies.
            assert record["y"] in (None, 0, 1)
            if record["matched_event"] is not None:
                assert record["matched_event"]["trusted"] is False
    # The long horizons outrun the 119 s coverage: explicitly censored.
    assert any(r["status"] in ("CENSORED", "UNTRUSTED_INFO") for r in report[300.0])


def _cfg(**overrides) -> PolicyConfig:
    values = dict(
        policy_version="policy-v1",
        representative_source="TMAX",
        upper_on_c=6.5,
        lower_off_c=3.5,
        thermal_max_age_s=120.0,
        command_max_future_skew_s=300.0,
        broker_offline_grace_s=30.0,
        backend_state_max_age_s=60.0,
        safe_local_exit_min_stable_s=60.0,
        predictive_enabled=False,
    )
    values.update(overrides)
    return PolicyConfig(**values)


def test_path3_no_model_falls_back_to_reactive_local_protection():
    view = label_records_to_prediction_view("W10-02", 60.0)
    assert view["risk_score"] is None
    assert view["health"] == ModelHealth.UNAVAILABLE
    cfg = _cfg(
        predictive_enabled=True,
        watch_threshold=0.6,
        preemptive_threshold=0.8,
        persistence_required_s=60.0,
        prediction_max_age_s=600.0,
    )
    policy_input = PolicyInput(
        device_mode=DeviceMode.ONLINE_NORMAL,
        thermal=ThermalView(quality=QualityState.VALID, t_representative_c=5.0, age_s=10.0),
        applied_cooling=CoolingState.OFF,
        remote=RemotePathView(
            broker_connected=True, broker_offline_s=0.0,
            backend_state_synced=True, backend_state_age_s=5.0,
            state_sync_trusted=True, remote_command_path_trusted=True,
            network_stable_s=600.0, stale_command_pending=False,
        ),
        current_state=PolicyState.NORMAL,
        fan_available=True,
        electrical_quality=QualityState.VALID,
        door_state="CLOSED",
        prediction=PredictionView(**{
            k: v for k, v in view.items()
            if k in PredictionView.__dataclass_fields__ and k != "series_run_id"
        }),
    )
    decision = evaluate_policy(policy_input, cfg)
    # Member D hears "no model" and falls back to local deterministic
    # protection: with this (remote-trusted, in-band) input the decision is
    # SAFE_LOCAL with the AI_UNAVAILABLE reason; predictive advice never used.
    assert decision.state == PolicyState.SAFE_LOCAL
    assert decision.reason_code.value == "AI_UNAVAILABLE"
    assert decision.predictive_blocked is True
    assert decision.actuation_intent.value == "HOLD"


def test_path4_measured_door_envelope_drives_d_policy_without_threshold_freeze():
    sidecar = json.loads(W13_SIDECAR.read_text(encoding="utf-8"))
    # The critical-Tmean threshold is explicitly NOT_FROZEN_PENDING_MEMBER_D.
    assert sidecar["critical_tmean_c"] is None
    assert sidecar["critical_tmean_status"] == "NOT_FROZEN_PENDING_MEMBER_D"
    views = door_critical_sidecar_to_policy_views(sidecar)
    assert views, "the committed sidecar carries no measurable run envelopes"
    measured = views[0]
    assert measured["replay"] is True
    assert measured["frames"] == 120
    # Member A measured real chamber air near ambient (a warm chamber).
    assert measured["thermal"]["t_representative_c"] == pytest.approx(29.79, abs=0.5)

    policy_input = PolicyInput(
        device_mode=DeviceMode.ONLINE_NORMAL,
        thermal=ThermalView(**measured["thermal"]),
        applied_cooling=CoolingState.OFF,
        remote=RemotePathView(
            broker_connected=True, broker_offline_s=0.0,
            backend_state_synced=True, backend_state_age_s=5.0,
            state_sync_trusted=True, remote_command_path_trusted=True,
            network_stable_s=600.0, stale_command_pending=False,
        ),
        current_state=PolicyState.NORMAL,
        fan_available=True,
        electrical_quality=QualityState.VALID,
        door_state="OPEN",
    )
    decision = evaluate_policy(policy_input, _cfg())
    # D's own frozen boundary (6.5 C) decides against A's measured value:
    # the warm chamber crosses it -> reactive CRITICAL_PROTECTION, cooling ON.
    assert decision.state == PolicyState.CRITICAL_PROTECTION
    assert decision.actuation_intent.value == "ON"
    assert decision.controller_id.value == "REACTIVE"


def test_path4_adapter_refuses_a_changed_freeze_state():
    sidecar = json.loads(W13_SIDECAR.read_text(encoding="utf-8"))
    tampered = dict(sidecar, critical_tmean_status="FROZEN")
    with pytest.raises(ValueError, match="freeze state changed"):
        door_critical_sidecar_to_policy_views(tampered)
