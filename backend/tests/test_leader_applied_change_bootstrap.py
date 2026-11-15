"""Applied-change bootstrap fixture — the path to the 28th real feature.

HOST/SOFTWARE TEST with clearly-labelled SYNTHETIC rows. It proves the
software path that turns a genuine physical applied-state transition into
``time_since_confirmed_applied_change`` and unlocks the frozen 28-feature
scoring. It does NOT claim a real transition or a real 28/28 inference:
today's live inference stays blocked until the actuator build runs and the
device reports a real applied change.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))

from leader_live_inference import (  # noqa: E402
    FeatureIncomplete, compute_features,
)
from leader_live_inference import Row  # noqa: E402

T0 = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
BOOT = "fixture-boot-001"


def row(offset_s: float = 0.0, **overrides) -> Row:
    values = dict(
        received_at=T0 + timedelta(seconds=offset_s),
        boot_id=BOOT,
        t1_c=24.1, t3_c=23.9, t4_c=24.2, t_air_c=24.8, rh_pct=65.0,
        door_state="CLOSED",
        thermal_valid=True, environment_valid=True, electrical_valid=True,
        applied_cooling="OFF", applied_duty=0.0,
        cooling_voltage_v=11.96, cooling_current_a=0.0,
        cooling_power_w=0.0, energy_counter_wh=136.0,
    )
    values.update(overrides)
    return Row(**values)


def test_no_applied_change_leaves_feature_none():
    rows = [row(0), row(1), row(2)]  # constant OFF/0: no transition
    features = compute_features(rows)
    assert features["time_since_confirmed_applied_change"] is None


def test_real_transition_births_the_feature():
    # OFF for 10 s, then a genuine applied ON at 60 %: the feature is the
    # age of that transition at the anchor.
    rows = [
        row(0), row(5), row(10),
        row(15, applied_cooling="ON", applied_duty=600.0),
        row(16, applied_cooling="ON", applied_duty=600.0),
    ]
    features = compute_features(rows)
    age = features["time_since_confirmed_applied_change"]
    assert age is not None and abs(age - 1.0) < 0.001


def test_duty_change_alone_counts_as_an_applied_change():
    rows = [
        row(0, applied_cooling="ON", applied_duty=200.0),
        row(5, applied_cooling="ON", applied_duty=400.0),
        row(6, applied_cooling="ON", applied_duty=400.0),
    ]
    features = compute_features(rows)
    assert features["time_since_confirmed_applied_change"] is not None
    assert abs(features["time_since_confirmed_applied_change"] - 1.0) < 0.001


def test_feature_never_crosses_boots():
    # The transition lived in a PREVIOUS boot: the current boot's feature
    # stays None (per-boot semantics, no history reuse).
    rows = [
        row(0, boot_id="boot-earlier"),
        row(1, boot_id="boot-earlier", applied_cooling="ON", applied_duty=600.0),
        row(100, boot_id=BOOT),
        row(101, boot_id=BOOT),
    ]
    features = compute_features(rows)
    assert features["time_since_confirmed_applied_change"] is None


def test_frozen_gate_blocks_incomplete_vector():
    rows = [row(0), row(1)]  # no transition -> the 28th feature is None
    features = compute_features(rows)
    missing = sorted(k for k, v in features.items() if v is None)
    assert "time_since_confirmed_applied_change" in missing
    with pytest.raises(FeatureIncomplete) as excinfo:
        if missing:
            raise FeatureIncomplete(missing)
    assert "time_since_confirmed_applied_change" in excinfo.value.missing
