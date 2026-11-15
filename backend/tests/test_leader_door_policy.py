"""Host tests for the Leader door-aware orchestration state machine.

Synthetic fixtures only (labelled HOST TEST): no device, no broker, no
database. Every safety rule of leader_door_policy.step is exercised,
including the fail-closed and idempotence properties the demo depends on.
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

OPEN_DOOR = DoorObservation(attested=True, state="OPEN", fresh=True, transitions=3)
CLOSED_DOOR = DoorObservation(attested=True, state="CLOSED", fresh=True, transitions=4,
                              closed_since_s=5.0)
FRESH_CLOSED_SOON = DoorObservation(attested=True, state="CLOSED", fresh=True, transitions=4,
                                    closed_since_s=0.5)
UNATTESTED = DoorObservation(attested=False, state=None, fresh=True, transitions=0)
STALE = DoorObservation(attested=True, state="OPEN", fresh=False, transitions=3)

CFG = DoorPolicyConfig(enabled=True, resume_dwell_s=2.0)
OFF_CFG = DoorPolicyConfig(enabled=False)


def inp(door, applied="ON", intent="ON", state="NORMAL", now=100.0):
    return DoorControlInput(door=door, applied_cooling=applied, policy_intent=intent,
                            policy_state=state, now_s=now)


def test_disabled_config_is_pure_passthrough():
    d = step(IDLE, inp(OPEN_DOOR), OFF_CFG)
    assert d.action == ACTION_NONE and d.reason == "DOOR_DEMO_MODE_DISABLED"
    assert d.state == IDLE


def test_suspend_on_attested_open_with_cooling_applied():
    d = step(IDLE, inp(OPEN_DOOR, applied="ON"), CFG)
    assert d.action == ACTION_ISSUE_OFF and d.reason == "DOOR_OPEN_SUSPEND"
    assert d.state == SUSPENDED


def test_open_door_with_cooling_already_off_is_noop():
    d = step(IDLE, inp(OPEN_DOOR, applied="OFF"), CFG)
    assert d.action == ACTION_NONE and d.reason == "DOOR_OPEN_ALREADY_OFF"


def test_suspended_holds_while_door_open():
    d = step(SUSPENDED, inp(OPEN_DOOR, applied="OFF"), CFG)
    assert d.action == ACTION_NONE and d.reason == "DOOR_STILL_OPEN"
    assert d.state == SUSPENDED


def test_resume_requires_dwell():
    d = step(SUSPENDED, inp(FRESH_CLOSED_SOON, applied="OFF", intent="ON"), CFG)
    assert d.action == ACTION_NONE and d.reason == "DOOR_CLOSED_DEBOUNCE"
    assert d.state == SUSPENDED


def test_resume_issues_on_only_when_member_policy_allows():
    d = step(SUSPENDED, inp(CLOSED_DOOR, applied="OFF", intent="ON"), CFG)
    assert d.action == ACTION_ISSUE_ON and d.reason == "DOOR_CLOSED_RESUME_ALLOWED"
    assert d.state == IDLE


def test_close_with_member_disallow_never_turns_on():
    d = step(SUSPENDED, inp(CLOSED_DOOR, applied="OFF", intent="HOLD"), CFG)
    assert d.action == ACTION_NONE and d.reason == "DOOR_CLOSED_NO_COOLING_REQUEST"
    assert d.state == IDLE
    d2 = step(SUSPENDED, inp(CLOSED_DOOR, applied="OFF", intent="OFF"), CFG)
    assert d2.action == ACTION_NONE and d2.state == IDLE


def test_closed_door_in_idle_is_noop():
    d = step(IDLE, inp(CLOSED_DOOR, applied="OFF", intent="HOLD"), CFG)
    assert d.action == ACTION_NONE and d.reason == "DOOR_CLOSED_NORMAL"


def test_unattested_door_blocks_everything():
    d = step(IDLE, inp(UNATTESTED, applied="ON"), CFG)
    assert d.action == ACTION_NONE and d.reason == "DOOR_NOT_ATTESTED"
    d2 = step(SUSPENDED, inp(UNATTESTED, applied="OFF"), CFG)
    assert d2.action == ACTION_NONE and d2.state == SUSPENDED


def test_stale_door_blocks_everything_and_holds_state():
    d = step(IDLE, inp(STALE, applied="ON"), CFG)
    assert d.action == ACTION_NONE and d.reason == "DOOR_EVIDENCE_STALE"
    d2 = step(SUSPENDED, inp(STALE, applied="OFF"), CFG)
    assert d2.action == ACTION_NONE and d2.state == SUSPENDED


@pytest.mark.parametrize("state", ["FAULT_LOCKOUT", "SAFE_LOCAL"])
def test_member_lockout_states_dominate(state):
    d = step(IDLE, inp(OPEN_DOOR, applied="ON", state=state), CFG)
    assert d.action == ACTION_NONE and d.reason == "MEMBER_POLICY_LOCKOUT"
    d2 = step(SUSPENDED, inp(CLOSED_DOOR, applied="OFF", intent="ON", state=state), CFG)
    assert d2.action == ACTION_NONE and d2.reason == "MEMBER_POLICY_LOCKOUT"


def test_idempotence_same_inputs_same_outputs():
    a = step(IDLE, inp(OPEN_DOOR, applied="ON"), CFG)
    b = step(IDLE, inp(OPEN_DOOR, applied="ON"), CFG)
    assert a == b


def test_member_cooling_request_carries_to_command():
    d = step(IDLE, inp(CLOSED_DOOR, applied="OFF", intent="ON"), CFG)
    assert d.action == ACTION_ISSUE_ON and d.reason == "MEMBER_POLICY_COOLING_REQUEST"


def test_member_stop_request_carries_to_command():
    d = step(IDLE, inp(CLOSED_DOOR, applied="ON", intent="OFF"), CFG)
    assert d.action == ACTION_ISSUE_OFF and d.reason == "MEMBER_POLICY_COOLING_STOP"


def _inp_cooldown(door, applied, intent):
    return DoorControlInput(door=door, applied_cooling=applied, policy_intent=intent,
                            policy_state="NORMAL", cooldown_active=True)


def test_cooldown_blocks_new_commands():
    d = step(IDLE, _inp_cooldown(CLOSED_DOOR, "OFF", "ON"), CFG)
    assert d.action == ACTION_NONE and d.reason == "COMMAND_COOLDOWN"
    d2 = step(SUSPENDED, _inp_cooldown(CLOSED_DOOR, "OFF", "ON"), CFG)
    # Even the resume path respects the cooldown: one command per transition.
    assert d2.action == ACTION_NONE and d2.reason == "COMMAND_COOLDOWN"
    assert d2.state == SUSPENDED


def test_suspend_overrides_member_cooling_request():
    # Door opens while member policy still asks for cooling: the door overlay
    # wins, cooling is suspended.
    d = step(IDLE, inp(OPEN_DOOR, applied="ON", intent="ON"), CFG)
    assert d.action == ACTION_ISSUE_OFF and d.reason == "DOOR_OPEN_SUSPEND"


def test_full_cycle_sequence():
    observations = [
        (IDLE, inp(CLOSED_DOOR, applied="OFF", intent="HOLD")),      # normal
        (IDLE, inp(OPEN_DOOR, applied="ON")),                        # open -> suspend
        (SUSPENDED, inp(OPEN_DOOR, applied="OFF")),                  # holds
        (SUSPENDED, inp(FRESH_CLOSED_SOON, applied="OFF")),          # debounce
        (SUSPENDED, inp(CLOSED_DOOR, applied="OFF", intent="OFF")),  # no resume
        (IDLE, inp(CLOSED_DOOR, applied="OFF", intent="HOLD")),      # normal
    ]
    results = [step(state, i, CFG) for state, i in observations]
    assert [r.action for r in results] == [
        ACTION_NONE, ACTION_ISSUE_OFF, ACTION_NONE, ACTION_NONE, ACTION_NONE, ACTION_NONE]
    assert [r.state for r in results] == [IDLE, SUSPENDED, SUSPENDED, SUSPENDED, IDLE, IDLE]
