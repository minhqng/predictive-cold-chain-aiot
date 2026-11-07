"""Unit and contract tests for Digital Twin core (C-W04-01 through C-W04-04).

Covers:
- C-W04-01: device_twin persistence and schema invariants.
- C-W04-02: Reported updater mutates reported_state only from validated telemetry;
  preserves desired and derived domains.
- C-W04-03: Desired updater updates backend intent only, with optimistic
  concurrency checking (expected_version) and no mutation to reported_state.
- C-W04-04: Freshness guards:
  - Exact duplicate (same boot, same seq) does not increment version or change state.
  - Out-of-order sequence (same boot, seq < last_seq) does not regress twin.
  - Old-boot replay (boot with earlier timestamp) does not overwrite active twin.
  - Reboot transitions (newer timestamp) cleanly update boot_id and seq.
  - Derived updater updates derived_state without altering reported or desired.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine

from coldguard_backend.twin_store import (
    _METADATA,
    device_twin,
    fetch_twin,
    update_twin_derived,
    update_twin_desired,
    update_twin_reported,
)


@pytest.fixture
def engine():
    """Isolated SQLite engine with device_twin schema for fast unit testing."""
    eng = create_engine("sqlite:///:memory:")
    _METADATA.create_all(eng)
    return eng


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def test_twin_persistence_and_initial_reported(engine):
    """C-W04-01 & C-W04-02: creating a twin from first valid observation."""
    t0 = _utcnow()
    state = {"t1_c": 4.5, "door_state": "CLOSED", "cooling_power_w": 12.0}

    res = update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-01",
        seq=1,
        state=state,
        reported_at=t0,
    )
    assert res["outcome"] == "updated"
    assert res["twin_version"] == 1

    twin = fetch_twin(engine, "coldguard-001")
    assert twin is not None
    assert twin["device_id"] == "coldguard-001"
    assert twin["reported_state"] == state
    assert twin["desired_state"] == {}
    assert twin["derived_state"] == {}
    assert twin["twin_version"] == 1
    assert twin["last_boot_id"] == "boot-01"
    assert twin["last_seq"] == 1
    assert twin["reported_at"] is not None


def test_reported_updater_preserves_desired_and_derived(engine):
    """C-W04-02: reported updates never overwrite desired or derived state."""
    t0 = _utcnow()
    update_twin_desired(
        engine,
        device_id="coldguard-001",
        desired_state={"cooling": "ON", "duty": 0.75},
        desired_at=t0,
    )
    update_twin_derived(
        engine,
        device_id="coldguard-001",
        derived_state={"risk_score": 0.85, "horizon_s": 300},
        derived_at=t0,
    )

    t1 = t0 + timedelta(seconds=1)
    rep_state = {"t1_c": 5.2, "door_state": "CLOSED"}
    res = update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-01",
        seq=10,
        state=rep_state,
        reported_at=t1,
    )
    assert res["outcome"] == "updated"

    twin = fetch_twin(engine, "coldguard-001")
    assert twin is not None
    assert twin["reported_state"] == rep_state
    assert twin["desired_state"] == {"cooling": "ON", "duty": 0.75}
    assert twin["derived_state"] == {"risk_score": 0.85, "horizon_s": 300}
    assert twin["twin_version"] == 3


def test_desired_updater_concurrency_and_isolation(engine):
    """C-W04-03: desired updater does not mutate reported state; supports expected_version."""
    t0 = _utcnow()
    update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-01",
        seq=1,
        state={"t1_c": 3.8},
        reported_at=t0,
    )

    # Valid desired update
    res1 = update_twin_desired(
        engine,
        device_id="coldguard-001",
        desired_state={"cooling": "ON", "duty": 0.5},
        expected_version=1,
    )
    assert res1["outcome"] == "updated"
    assert res1["twin_version"] == 2

    twin = fetch_twin(engine, "coldguard-001")
    assert twin["reported_state"] == {"t1_c": 3.8}
    assert twin["desired_state"] == {"cooling": "ON", "duty": 0.5}

    # Version mismatch conflict
    res_conflict = update_twin_desired(
        engine,
        device_id="coldguard-001",
        desired_state={"cooling": "OFF", "duty": 0.0},
        expected_version=1,  # actual is 2
    )
    assert res_conflict["outcome"] == "version_conflict"
    assert res_conflict["current_version"] == 2
    assert res_conflict["expected_version"] == 1


def test_freshness_guard_exact_duplicate(engine):
    """C-W04-04: identical (boot_id, seq) redelivery does not mutate twin or increment version."""
    t0 = _utcnow()
    update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-01",
        seq=100,
        state={"t1_c": 4.0},
        reported_at=t0,
    )

    # Redelivery of same seq=100
    res = update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-01",
        seq=100,
        state={"t1_c": 99.9},  # conflicting payload attempted
        reported_at=t0,
    )
    assert res["outcome"] == "exact_duplicate"
    assert res["twin_version"] == 1

    twin = fetch_twin(engine, "coldguard-001")
    assert twin["reported_state"] == {"t1_c": 4.0}
    assert twin["last_seq"] == 100


def test_freshness_guard_out_of_order_sequence(engine):
    """C-W04-04: out-of-order delivery (seq 100 -> seq 102 -> seq 101) never regresses twin."""
    t0 = _utcnow()
    # First: seq=100
    update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-01",
        seq=100,
        state={"seq": 100, "t1_c": 4.0},
        reported_at=t0,
    )

    # Second: seq=102 arrives before 101
    t2 = t0 + timedelta(seconds=2)
    update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-01",
        seq=102,
        state={"seq": 102, "t1_c": 4.2},
        reported_at=t2,
    )

    twin_after_102 = fetch_twin(engine, "coldguard-001")
    assert twin_after_102["last_seq"] == 102
    assert twin_after_102["reported_state"]["seq"] == 102
    ver_after_102 = twin_after_102["twin_version"]

    # Third: delayed seq=101 arrives late
    t1 = t0 + timedelta(seconds=1)
    res_late = update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-01",
        seq=101,
        state={"seq": 101, "t1_c": 4.1},
        reported_at=t1,
    )
    assert res_late["outcome"] == "stale_seq"

    # Twin remains at seq=102 with version unchanged
    twin_final = fetch_twin(engine, "coldguard-001")
    assert twin_final["last_seq"] == 102
    assert twin_final["reported_state"]["seq"] == 102
    assert twin_final["twin_version"] == ver_after_102


def test_freshness_guard_reboot_and_old_boot_replay(engine):
    """C-W04-04: valid reboot advances state, but old-boot historical replay does not regress twin."""
    t0 = _utcnow()
    update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-active-02",
        seq=50,
        state={"boot": "boot-active-02", "seq": 50},
        reported_at=t0,
    )

    # An old boot replay (boot-old-01) with older captured_at arrives
    t_old = t0 - timedelta(hours=2)
    res_old = update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-old-01",
        seq=999,  # Even with high seq, it's an old boot
        state={"boot": "boot-old-01", "seq": 999},
        reported_at=t_old,
    )
    assert res_old["outcome"] == "stale_boot_replay"

    twin = fetch_twin(engine, "coldguard-001")
    assert twin["last_boot_id"] == "boot-active-02"
    assert twin["last_seq"] == 50
    assert twin["reported_state"]["boot"] == "boot-active-02"

    # A legitimate new reboot arrives (boot-new-03 with newer timestamp)
    t_new = t0 + timedelta(minutes=5)
    res_new = update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-new-03",
        seq=1,
        state={"boot": "boot-new-03", "seq": 1},
        reported_at=t_new,
    )
    assert res_new["outcome"] == "updated"

    twin_rebooted = fetch_twin(engine, "coldguard-001")
    assert twin_rebooted["last_boot_id"] == "boot-new-03"
    assert twin_rebooted["last_seq"] == 1
    assert twin_rebooted["reported_state"]["boot"] == "boot-new-03"


def test_derived_state_updater(engine):
    """Derived updater sets derived_state and advances twin_version without touching others."""
    t0 = _utcnow()
    update_twin_reported(
        engine,
        device_id="coldguard-001",
        boot_id="boot-01",
        seq=1,
        state={"t1_c": 4.0},
        reported_at=t0,
    )
    update_twin_desired(
        engine,
        device_id="coldguard-001",
        desired_state={"cooling": "ON"},
        desired_at=t0,
    )

    res = update_twin_derived(
        engine,
        device_id="coldguard-001",
        derived_state={"anomaly_score": 0.02, "model": "xgboost-v1"},
        derived_at=t0,
    )
    assert res["outcome"] == "updated"
    assert res["twin_version"] == 3

    twin = fetch_twin(engine, "coldguard-001")
    assert twin["reported_state"] == {"t1_c": 4.0}
    assert twin["desired_state"] == {"cooling": "ON"}
    assert twin["derived_state"] == {"anomaly_score": 0.02, "model": "xgboost-v1"}
