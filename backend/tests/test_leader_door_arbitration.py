"""Door-aware arbitration matrix — the nine demo arbitration scenarios.

Each test is one row of the arbitration matrix demanded by the commissioning
handoff: real reason codes, real precedence, no scenario in which the door
overlay overrides a member protection. Synthetic fixtures only (HOST TEST).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))

from leader_door_policy import (  # noqa: E402
    IDLE, SUSPENDED,
    ACTION_ISSUE_OFF, ACTION_ISSUE_ON, ACTION_NONE,
    DoorControlInput, DoorObservation, DoorPolicyConfig, step,
)

CFG = DoorPolicyConfig(enabled=True, resume_dwell_s=2.0)

OPEN = DoorObservation(attested=True, state="OPEN", fresh=True, transitions=3)
CLOSED = DoorObservation(attested=True, state="CLOSED", fresh=True, transitions=4,
                         closed_since_s=5.0)
CLOSED_FRESH = DoorObservation(attested=True, state="CLOSED", fresh=True, transitions=4,
                               closed_since_s=0.5)
UNATTESTED = DoorObservation(attested=False, state=None, fresh=True, transitions=0)
STALE_DOOR = DoorObservation(attested=True, state="OPEN", fresh=False, transitions=3)


def inp(door, applied="OFF", intent="HOLD", state="NORMAL", cooldown=False):
    return DoorControlInput(door=door, applied_cooling=applied, policy_intent=intent,
                            policy_state=state, cooldown_active=cooldown, now_s=100.0)


def test_1_open_normal_thermal_suspends():
    d = step(IDLE, inp(OPEN, applied="ON", intent="ON", state="NORMAL"), CFG)
    assert (d.action, d.reason, d.state) == (ACTION_ISSUE_OFF, "DOOR_OPEN_SUSPEND", SUSPENDED)


def test_2_open_critical_protection_never_suspends():
    d = step(IDLE, inp(OPEN, applied="ON", intent="ON", state="CRITICAL_PROTECTION"), CFG)
    assert (d.action, d.reason) == (ACTION_NONE, "MEMBER_CRITICAL_PROTECTION_ACTIVE")
    assert d.state == IDLE


def test_2b_protection_engaging_mid_suspension_yields_immediately():
    d = step(SUSPENDED, inp(OPEN, applied="OFF", intent="ON",
                            state="CRITICAL_PROTECTION"), CFG)
    assert (d.action, d.reason, d.state) == (
        ACTION_ISSUE_ON, "MEMBER_CRITICAL_PROTECTION_RESUME", IDLE)


def test_3_closed_cooling_required_resumes_after_dwell():
    d = step(SUSPENDED, inp(CLOSED, applied="OFF", intent="ON",
                            state="CRITICAL_PROTECTION"), CFG)
    # The protective yield outranks the demo resume: same action (ON), the
    # member-protection reason code, no dwell wait.
    assert (d.action, d.reason, d.state) == (
        ACTION_ISSUE_ON, "MEMBER_CRITICAL_PROTECTION_RESUME", IDLE)
    # Same scenario without the protection state takes the demo path.
    d2 = step(SUSPENDED, inp(CLOSED, applied="OFF", intent="ON",
                             state="NORMAL"), CFG)
    assert (d2.action, d2.reason, d2.state) == (
        ACTION_ISSUE_ON, "DOOR_CLOSED_RESUME_ALLOWED", IDLE)


def test_4_closed_cooling_not_required_stays_off():
    d = step(SUSPENDED, inp(CLOSED, applied="OFF", intent="OFF", state="NORMAL"), CFG)
    assert (d.action, d.reason, d.state) == (
        ACTION_NONE, "DOOR_CLOSED_NO_COOLING_REQUEST", IDLE)
    d2 = step(IDLE, inp(CLOSED, applied="OFF", intent="HOLD", state="NORMAL"), CFG)
    assert d2.action == ACTION_NONE and d2.reason == "DOOR_CLOSED_NORMAL"


def test_5_unknown_door_blocks_everything():
    d = step(IDLE, inp(UNATTESTED, applied="ON", intent="ON"), CFG)
    assert (d.action, d.reason) == (ACTION_NONE, "DOOR_NOT_ATTESTED")
    d2 = step(SUSPENDED, inp(UNATTESTED, applied="OFF"), CFG)
    assert d2.action == ACTION_NONE and d2.state == SUSPENDED


def test_6_stale_telemetry_blocks_everything():
    d = step(IDLE, inp(STALE_DOOR, applied="ON", intent="ON"), CFG)
    assert (d.action, d.reason) == (ACTION_NONE, "DOOR_EVIDENCE_STALE")


@pytest.mark.parametrize("state", ["FAULT_LOCKOUT", "SAFE_LOCAL"])
def test_7_active_fault_locks_the_overlay_out(state):
    d = step(IDLE, inp(OPEN, applied="ON", intent="ON", state=state), CFG)
    assert (d.action, d.reason) == (ACTION_NONE, "MEMBER_POLICY_LOCKOUT")


def test_8_unsynchronized_clock_reaches_the_matrix_via_stale_inputs():
    # An unsynchronized device degrades freshness upstream (the evidence layer
    # marks frames stale / the clock view unanchored); the machine's contract
    # is that ANY non-fresh input blocks. Represented here by the stale flag.
    d = step(IDLE, inp(STALE_DOOR, applied="ON"), CFG)
    assert d.action == ACTION_NONE


def test_9_previously_applied_states_are_respected():
    # Applied ON + member satisfied (HOLD) with door closed: nothing to do.
    d = step(IDLE, inp(CLOSED, applied="ON", intent="HOLD"), CFG)
    assert d.action == ACTION_NONE and d.reason == "DOOR_CLOSED_NORMAL"
    # Applied ON + member wants OFF: the stop request is carried.
    d2 = step(IDLE, inp(CLOSED, applied="ON", intent="OFF"), CFG)
    assert (d2.action, d2.reason) == (ACTION_ISSUE_OFF, "MEMBER_POLICY_COOLING_STOP")
    # Applied OFF + member wants ON: the start request is carried.
    d3 = step(IDLE, inp(CLOSED, applied="OFF", intent="ON"), CFG)
    assert (d3.action, d3.reason) == (ACTION_ISSUE_ON, "MEMBER_POLICY_COOLING_REQUEST")


def test_cooldown_blocks_the_immediate_resume():
    d = step(SUSPENDED, inp(CLOSED, applied="OFF", intent="ON",
                            state="CRITICAL_PROTECTION", cooldown=True), CFG)
    assert (d.action, d.reason, d.state) == (
        ACTION_NONE, "COMMAND_COOLDOWN", SUSPENDED)
