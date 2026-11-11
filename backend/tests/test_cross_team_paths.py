"""Executable cross-team path checks for the six W01-W13 integration paths.

Paths 1, 5 and 6 run real member code (no member source modified) over
committed evidence with backend-only dependencies. Paths 2-4 additionally need
Member B's ``coldguard_ml`` dependencies and live in
``tests/test_cross_team_data_paths.py`` (honest skip when absent).
"""

import json
import pathlib
import sys
from datetime import datetime, timezone
from threading import Event

import pytest

from coldguard_backend.command_path_runner import run_command_path

from coldguard_control.commands import LocalSafetyEvidence
from coldguard_control.config import PolicyConfig
from coldguard_control.policy import (
    PolicyInput,
    PredictionView,
    RemotePathView,
    ThermalView,
)
from coldguard_control.types import (
    CoolingState,
    DeviceMode,
    ModelHealth,
    PolicyState,
    QualityState,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
W06_DEMO = ROOT / "evidence" / "A" / "W06" / "demo-command-capture.log"

# --- path 1: A -> C, real gateway over a committed capture ------------------


class _FakeStream:
    def __init__(self, data: bytes):
        self.data = data

    def read(self, n):
        out, self.data = self.data[:n], self.data[n:]
        return out


class _FakePub:
    def __init__(self):
        self.published = []
        self.poll = lambda timeout=0: None

    def publish(self, topic, payload):
        self.published.append((topic, payload))


def test_path1_real_gateway_translates_committed_capture_frames():
    sys.path.insert(0, str(ROOT / "backend" / "scripts"))
    import serial_gateway as gw

    data = ("\n".join(W06_DEMO.read_text(encoding="utf-8").splitlines()) + "\n").encode()
    pub = _FakePub()
    gw.pump(_FakeStream(data), pub, topic="coldguard/coldguard-001/telemetry",
            replay=True, stop=Event())
    assert pub.published, "the real gateway translated nothing from A's capture"
    topic, payload = pub.published[0]
    assert topic == "coldguard/coldguard-001/telemetry"
    body = json.loads(payload)
    assert body["schema_version"] == 2
    assert body["device_id"] == "coldguard-001"
    assert body["captured_at"] is None  # clockless serial: no invented event time
    # The real gateway skips CMDACK frames (their own contract) — the framed
    # teardown below is why path 6 needs the owner bridge on the uplink.
    for _, extra in pub.published:
        assert "CMDACK" not in extra.decode("ascii", errors="ignore")


# --- paths 5 and 6 are proven by the dedicated command-path suites ----------


def test_paths_5_and_6_end_to_end_through_the_owner_runner():
    from coldguard_backend.command_path_runner import FixtureAckDevice

    outcome = run_command_path(
        PolicyInput(
            device_mode=DeviceMode.ONLINE_NORMAL,
            thermal=ThermalView(quality=QualityState.VALID, t_representative_c=7.2, age_s=10.0),
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
                health=ModelHealth.READY, model_version="m-v1",
                feature_version="f-v1", risk_score=0.9, age_s=5.0,
                horizon_s=300.0, above_preemptive_s=90.0,
            ),
        ),
        PolicyConfig(
            policy_version="policy-v1", representative_source="TMAX",
            upper_on_c=6.5, lower_off_c=3.5, thermal_max_age_s=120.0,
            command_max_future_skew_s=300.0, broker_offline_grace_s=30.0,
            backend_state_max_age_s=60.0, safe_local_exit_min_stable_s=60.0,
            predictive_enabled=True, watch_threshold=0.6,
            preemptive_threshold=0.8, persistence_required_s=60.0,
            prediction_max_age_s=600.0,
        ),
        LocalSafetyEvidence(
            device_mode=DeviceMode.ONLINE_NORMAL,
            policy_state=PolicyState.NORMAL,
            thermal_quality=QualityState.VALID,
            thermal_age_s=10.0,
            fan_available=True,
        ),
        command_id="00000000-0000-4000-8000-0000000000c5",
        device_id="coldguard-001",
        issued_at=datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc),
        device_boundary=FixtureAckDevice("synchronized-accepted"),
        clock_synchronized=True,  # SIMULATION_ONLY fixture claim
    )
    # path 5: desired (D PREEMPTIVE) -> accepted -> dispatched (A record).
    assert outcome.desired_decision["actuation_intent"] == "ON"
    assert outcome.command_verification["status"] == "ACCEPTED"
    assert outcome.dispatched_record is not None
    # path 6: ACK -> C envelope -> A's stage ledger (blocked honestly).
    assert outcome.ack_command_envelope["status"] == "ACCEPTED"
    assert outcome.blocked_at == "APPLIED_STATE"


# --- residual blockers recorded as data, in one place ------------------------

# Paths 2-4 tests live in tests/test_cross_team_data_paths.py (they need
# Member B's ml dependency set). Board entries are plain names, not references.
PATH_STATUSES = {
    1: {"path": "A->C telemetry", "status": "OWNER_RUNNER_INTEGRATED",
        "test": "test_cross_team_paths.py::test_path1_real_gateway_translates_committed_capture_frames",
        "note": "real gateway code offline; MQTT PUBACK not exercised here"},
    2: {"path": "C->B observation admission", "status": "OWNER_RUNNER_INTEGRATED",
        "test": "test_cross_team_data_paths.py::test_path2_committed_accepted_s2_run_admits_into_b_contract",
        "note": "committed DATASET_ACCEPTED_S2 rows; clockless encodings refused honestly"},
    3: {"path": "B->D predictive hand-off", "status": "CONTRACT_VERIFIED",
        "test": "test_cross_team_data_paths.py::test_path3_no_model_falls_back_to_reactive_local_protection",
        "note": "no B model exists at W13; UNAVAILABLE hand-off + D fallback verified"},
    4: {"path": "A->D thermal/door -> policy", "status": "OWNER_RUNNER_INTEGRATED",
        "test": "test_cross_team_data_paths.py::test_path4_measured_door_envelope_drives_d_policy_without_threshold_freeze",
        "note": "committed measured envelopes; critical-Tmean freeze stays with D"},
    5: {"path": "D->C->A command", "status": "OWNER_RUNNER_INTEGRATED",
        "test": "test_cross_team_paths.py::test_paths_5_and_6_end_to_end_through_the_owner_runner",
        "note": "device boundary is A's committed fixture; firmware not executed"},
    6: {"path": "A->C->D ACK lifecycle", "status": "OWNER_RUNNER_INTEGRATED",
        "test": "test_cross_team_paths.py::test_paths_5_and_6_end_to_end_through_the_owner_runner",
        "note": "stage promotion is Member A's trace tool; no stage assumed"},
}


def test_six_path_board_is_complete_and_does_not_overclaim():
    assert set(PATH_STATUSES) == set(range(1, 7))
    forbidden = {"REAL_SERVICE_VERIFIED", "PHYSICAL_VERIFIED"}
    for path_id, entry in PATH_STATUSES.items():
        assert entry["status"] not in forbidden, path_id
        filename, test_name = entry["test"].split("::")
        assert test_name.startswith("test_"), path_id
        assert (pathlib.Path(__file__).parent / filename).exists(), path_id
