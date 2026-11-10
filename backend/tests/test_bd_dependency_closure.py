"""Phase 2B: executable B→D data-dependency closure checks.

Drives Member B's real pipeline order (admit → grouped split → windows →
label verdicts) over the committed 18-run physical dataset's nine
DATASET_ACCEPTED runs, then Member D's PredictionView mapping. Nothing is
invented: no critical-Tmean threshold, no device EVENT_UTC, no y=1 label.
"""

import json
import pathlib
import sys

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
    evaluate_b_to_d_closure,
    load_accepted_runs,
    run_csv_to_c_rows,
)
from coldguard_control.types import ModelHealth  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLOSURE_SIDECAR = ROOT_PATH / "docs" / "owner-integration" / "w13-bd-closure" / "bd-dependency-closure-20261110.json"


@pytest.fixture(scope="module")
def closure() -> dict:
    return evaluate_b_to_d_closure()


def test_nine_accepted_runs_load_with_verified_hashes():
    runs = load_accepted_runs()
    assert len(runs) == 9
    kinds = {r["classification"].rsplit("_", 1)[1] for r in runs}
    assert kinds == {"S1", "S2"}
    assert {r["timebase"] for r in runs} == {"HOST_STAMP"}
    assert {r["device_timestamp_utc_source"] for r in runs} == {
        "DEVICE_HAS_NO_WALL_CLOCK"
    }
    assert all(r["hardware_config_id"] == "CG-HW-001" for r in runs)


def test_all_accepted_rows_admit_through_b_contract(closure: dict):
    rows = closure["runs"]
    assert len(rows) == 9
    frame_expect = {
        "W10-02": 120,
        "W10-03-run1": 300, "W10-03-run2": 300, "W10-03-run3": 300, "W10-03-run4": 300,
        "trial2": 600, "trial3": 600, "trial4": 601, "trial1-imported": 600,
    }
    for row in rows:
        assert row["admitted"] == frame_expect[row["run_tag"]] == row["rows"]
        assert row["refused"] == 0
        assert row["sha256_verified"] is True
        assert row["event_time_trust"] == "HOST_STAMP_DECLARED_NOT_DEVICE_VERIFIED"
    assert closure["totals"]["admitted"] == sum(frame_expect.values()) == 3721


def test_split_is_deterministic_and_respects_the_group_floor(closure: dict):
    again = evaluate_b_to_d_closure()
    assert again["split"]["train_runs"] == closure["split"]["train_runs"]
    assert again["split"]["validation_runs"] == closure["split"]["validation_runs"]
    assert again["split"]["test_runs"] == closure["split"]["test_runs"]
    for part in ("train_runs", "validation_runs", "test_runs"):
        assert len(closure["split"][part]) == 3  # min_groups_per_partition=3
    assert closure["split"]["controller_context"] == (
        "observational-capture-no-controller-in-loop"
    )


def test_mixed_historical_and_new_runs_stay_identity_disjoint(closure: dict):
    # trial1-imported is the historical capture (boot c20d17f6); the W10 runs
    # share boot 73311d0c. Boot-scoped identity keeps every sample distinct.
    boots = {r["run_tag"]: r["boot_id"] for r in closure["runs"]}
    assert boots["trial1-imported"] == "c20d17f6"
    assert boots["trial2"] == "4a21a645"
    assert boots["W10-03-run1"] == "73311d0c"
    all_ids = [
        (r["boot_id"], r["run_tag"]) for r in closure["runs"]
    ]
    assert len(all_ids) == len(set(all_ids))


def test_horizon_set_is_the_frozen_w13_vocabulary():
    assert W13_HORIZONS_S == (30.0, 60.0, 120.0, 300.0)


def test_door_runs_are_refused_by_b_though_unattested_ground_truth(closure: dict):
    """Door transitions are framing-only; B refuses labels, no y fabricated."""
    door_runs = ("W10-02", "W10-03-run1", "W10-03-run2", "W10-03-run3", "W10-03-run4")
    for run_tag in door_runs:
        verdicts = closure["labels"][run_tag]
        for horizon in W13_HORIZONS_S:
            verdict = verdicts[horizon]
            assert verdict["verdict"] == "REFUSED_GROUND_TRUTH_UNKNOWN"
            assert verdict["windows_labeled"] == 0
            assert "coverage unknown" in verdict["reason"]
    # And nowhere in the whole closure does a positive label exist.
    for run_tag, verdicts in closure["labels"].items():
        for verdict in verdicts.values():
            assert verdict.get("positive_labels", 0) == 0
            assert verdict["verdict"] != "EVALUATED"


def test_s1_runs_have_no_critical_state_info_and_are_not_labeled(closure: dict):
    for run_tag in ("trial1-imported", "trial2", "trial3", "trial4"):
        verdicts = closure["labels"][run_tag]
        for horizon in W13_HORIZONS_S:
            entry = verdicts[horizon]
            assert entry["verdict"] == "NO_CRITICAL_STATE_INFO"
            assert entry["windows_labeled"] == 0


def test_prediction_views_per_horizon_map_into_d_honestly(closure: dict):
    assert sorted(closure["prediction_views"]) == sorted(W13_HORIZONS_S)
    for horizon, view in closure["prediction_views"].items():
        assert horizon == view["horizon_s"]
        assert view["health"] == ModelHealth.UNAVAILABLE
        assert view["risk_score"] is None  # no B model exists at W13
        assert view["model_version"] == "NONE_MEMBER_B_W13"
    # ...and the D fallback executes against the real policy core per horizon:
    from coldguard_control.commands import LocalSafetyEvidence
    from coldguard_control.policy import (
        PolicyInput,
        PredictionView,
        RemotePathView,
        ThermalView,
        evaluate_policy,
    )
    from coldguard_control.config import PolicyConfig
    from coldguard_control.types import (
        CoolingState,
        DeviceMode,
        PolicyState,
        QualityState,
    )
    cfg = PolicyConfig(
        policy_version="policy-v1", representative_source="TMAX",
        upper_on_c=6.5, lower_off_c=3.5, thermal_max_age_s=120.0,
        command_max_future_skew_s=300.0, broker_offline_grace_s=30.0,
        backend_state_max_age_s=60.0, safe_local_exit_min_stable_s=60.0,
        predictive_enabled=True, watch_threshold=0.6,
        preemptive_threshold=0.8, persistence_required_s=60.0,
        prediction_max_age_s=600.0,
    )
    for view in closure["prediction_views"].values():
        policy_input = PolicyInput(
            device_mode=DeviceMode.ONLINE_NORMAL,
            thermal=ThermalView(
                quality=QualityState.VALID, t_representative_c=5.0, age_s=10.0
            ),
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
            prediction=PredictionView(
                health=view["health"],
                model_version=view["model_version"],
                feature_version=view["feature_version"],
                risk_score=view["risk_score"],
                age_s=view["age_s"],
                horizon_s=view["horizon_s"],
                above_preemptive_s=view["above_preemptive_s"],
            ),
        )
        decision = evaluate_policy(policy_input, cfg)
        assert decision.reason_code.value == "AI_UNAVAILABLE"
        assert decision.predictive_blocked is True
        assert decision.actuation_intent.value == "HOLD"


def test_unknown_door_rows_never_become_critical_state_events(closure):
    """UNKNOWN door_state is Member B's explicit refusal — no events from it."""
    import dataclasses

    from coldguard_backend.cross_team_paths import unattested_door_series

    run = next(r for r in load_accepted_runs() if r["run_tag"] == "W10-02")
    admitted = admit_rows(
        run_csv_to_c_rows(run["csv_path"], "W10-02")
    )["admitted"]
    source = next(o for o in admitted if o.door_state == "OPEN")
    unknown = dataclasses.replace(source, door_state="UNKNOWN", seq=source.seq + 1)
    series, verdict = unattested_door_series("W10-02", [unknown])
    assert series is None
    assert verdict["verdict"] == "NO_CRITICAL_STATE_INFO"


def test_closure_sidecar_matches_the_deterministic_execution(closure):
    """The committed sidecar is this exact code's own deterministic output."""
    assert CLOSURE_SIDECAR.exists()
    committed = json.loads(CLOSURE_SIDECAR.read_text(encoding="utf-8"))
    committed = json.loads(json.dumps(committed, sort_keys=True, default=str))
    renewal = json.loads(json.dumps(closure, sort_keys=True, default=str))
    assert committed == renewal
