"""Leader-owned door-aware cooling orchestration (pure state machine).

Member D's frozen policy (control/src/coldguard_control/policy.py) validates
``door_state`` but never acts on it: its decision table has no door branch.
This module adds the door-aware demo behaviour OUTSIDE member code, as a
pure, fully host-testable state machine that a thin runner feeds with real
evidence and with Member D's real decision for the current tick.

Precedence (highest first):
1. Config off        -> pure passthrough: never issues anything (reversible).
2. Door unattested /
   stale             -> no action, fail-closed. A suspended state STAYS
                        suspended (cooling stays off) until fresh evidence.
3. Member D lockout /
   safe-local        -> no action: device-side safety dominates; the member
                        controller and its fault latching own the plant.
4. Door OPEN (attested, fresh) while cooling is applied -> issue OFF
   (DOOR_OPEN_SUSPEND) ONLY when the member is not in a protective state.
   In CRITICAL_PROTECTION the cooling IS the protective response (the
   member's own contract: "critical thermal protection dominates
   everything below"), so the overlay stands down and reports
   MEMBER_CRITICAL_PROTECTION_ACTIVE; if protection engages mid-suspension
   the overlay yields immediately (MEMBER_CRITICAL_PROTECTION_RESUME).
5. Door CLOSED + dwell satisfied -> re-evaluate THROUGH MEMBER D: issue ON
   only when Member D's fresh decision explicitly allows cooling
   (actuation_intent == ON). The door closing never switches the TEC on by
   itself; hysteresis/thresholds stay Member D's.
6. Door closed, member decision drives: intent ON while not applied ->
   issue ON; intent OFF while applied -> issue OFF. The layer only CARRIES
   the member's intent to the command path; it never invents one.
7. Cooldown: after any issued command, further commands wait until the
   applied-state feedback (or the cooldown window) resolves, so one door
   transition or one policy change produces exactly one command.

The machine never issues a command when the previous tick's command for the
same transition was already issued (state machine idempotence): each issued
command is exactly one per door transition, and the applied-state feedback
(the device's own report) confirms what actually happened.
"""

from __future__ import annotations

from dataclasses import dataclass

DOOR_POLICY_VERSION = "leader-door-demo-1"

IDLE = "IDLE"
SUSPENDED = "SUSPENDED"

ACTION_NONE = "NONE"
ACTION_ISSUE_OFF = "ISSUE_OFF"
ACTION_ISSUE_ON = "ISSUE_ON"

#: Member D policy states in which this layer must never issue anything:
#: the member controller's own safety states dominate the plant.
_MEMBER_LOCKOUT_STATES = frozenset({"FAULT_LOCKOUT", "SAFE_LOCAL"})

#: Member D's reactive protective state: the chamber is at/above the upper
#: boundary and COOLING IS THE PROTECTIVE RESPONSE ("critical thermal
#: protection dominates everything below" — the member's own contract).
#: The door overlay never suspends it, and yields immediately if it latches
#: while a suspension is active: the demo must never fight the protection.
_MEMBER_PROTECTED_STATES = frozenset({"CRITICAL_PROTECTION"})


@dataclass(frozen=True)
class DoorPolicyConfig:
    """Explicit, reversible configuration. ``enabled=False`` is pure
    passthrough: the layer observes and records but never issues."""

    enabled: bool = False
    #: Minimum time the door must have been CLOSED before a resume may be
    # evaluated (debounce/stability on top of the member's own debounce).
    resume_dwell_s: float = 2.0


@dataclass(frozen=True)
class DoorObservation:
    """Leader evidence-layer view of the door for THIS tick."""

    attested: bool          # per-boot attestation (both raw levels seen)
    state: str | None       # "OPEN"/"CLOSED" when attested, else None
    fresh: bool             # evidence freshness (stale -> no action)
    transitions: int        # device-reported door_transitions this boot
    closed_since_s: float | None = None  # seconds since the CLOSED transition


@dataclass(frozen=True)
class DoorControlInput:
    door: DoorObservation
    applied_cooling: str           # device-reported applied state: "ON"/"OFF"
    policy_intent: str             # Member D actuation_intent: "HOLD"/"OFF"/"ON"
    policy_state: str              # Member D policy state name
    cooldown_active: bool = False  # a command was just issued; wait for its
                                   # applied-state feedback before another
    now_s: float = 0.0


@dataclass(frozen=True)
class DoorControlDecision:
    action: str                    # ACTION_*: what the runner may issue
    reason: str
    state: str                     # resulting orchestration state
    detail: str = ""


def step(state: str, inp: DoorControlInput, cfg: DoorPolicyConfig) -> DoorControlDecision:
    """One deterministic step. Pure: no I/O, no clocks, no randomness."""
    if not cfg.enabled:
        return DoorControlDecision(
            ACTION_NONE, "DOOR_DEMO_MODE_DISABLED", IDLE,
            "passthrough: member policy governs unchanged")

    door = inp.door
    if not door.attested or door.state is None or not door.fresh:
        reason = ("DOOR_NOT_ATTESTED" if not door.attested
                  else "DOOR_EVIDENCE_STALE")
        return DoorControlDecision(
            ACTION_NONE, reason, state,
            "fail-closed: no door action without fresh per-boot attestation")

    if inp.policy_state in _MEMBER_LOCKOUT_STATES:
        return DoorControlDecision(
            ACTION_NONE, "MEMBER_POLICY_LOCKOUT", state,
            f"member policy state {inp.policy_state} dominates; no override")

    if inp.cooldown_active:
        # A command was just issued: wait for its applied-state feedback (or
        # the cooldown window) before anything else, in any state. One door
        # transition or one policy change must produce exactly one command.
        return DoorControlDecision(
            ACTION_NONE, "COMMAND_COOLDOWN", state,
            "a command was just issued; waiting for its applied-state feedback")

    if state == SUSPENDED:
        if inp.policy_state in _MEMBER_PROTECTED_STATES:
            # The member's reactive protection engaged while suspended: the
            # protective cooling demand wins over the demo immediately, with
            # no dwell wait.
            return DoorControlDecision(
                ACTION_ISSUE_ON, "MEMBER_CRITICAL_PROTECTION_RESUME", IDLE,
                "member protection demands cooling; the door overlay yields")
        if door.state == "OPEN":
            return DoorControlDecision(
                ACTION_NONE, "DOOR_STILL_OPEN", SUSPENDED,
                "cooling stays suspended while the door is open")
        # Door CLOSED: wait for the dwell, then re-evaluate THROUGH member D.
        since = door.closed_since_s
        if since is None or since < cfg.resume_dwell_s:
            return DoorControlDecision(
                ACTION_NONE, "DOOR_CLOSED_DEBOUNCE", SUSPENDED,
                f"closed {0.0 if since is None else round(since, 2)}s < "
                f"{cfg.resume_dwell_s}s dwell")
        if inp.policy_intent == "ON":
            return DoorControlDecision(
                ACTION_ISSUE_ON, "DOOR_CLOSED_RESUME_ALLOWED", IDLE,
                "member policy allows cooling; resuming after door closure")
        return DoorControlDecision(
            ACTION_NONE, "DOOR_CLOSED_NO_COOLING_REQUEST", IDLE,
            f"member policy intent {inp.policy_intent}; staying off, its own "
            "governance resumes")

    # state == IDLE
    if door.state == "OPEN":
        if inp.applied_cooling == "ON":
            if inp.policy_state in _MEMBER_PROTECTED_STATES:
                # Cooling IS the protective response right now (member's
                # reactive critical branch): the door overlay stands down
                # and reports the true reason instead of overriding it.
                return DoorControlDecision(
                    ACTION_NONE, "MEMBER_CRITICAL_PROTECTION_ACTIVE", IDLE,
                    "door open, but the member's critical protection demands "
                    "cooling; suspension refused")
            return DoorControlDecision(
                ACTION_ISSUE_OFF, "DOOR_OPEN_SUSPEND", SUSPENDED,
                "attested door open while cooling applied; suspending")
        return DoorControlDecision(
            ACTION_NONE, "DOOR_OPEN_ALREADY_OFF", IDLE,
            "door open, cooling already off")

    # Door closed: Member D's decision drives start/stop; this layer only
    # carries the member's intent to the command path and never invents one.
    if inp.policy_intent == "ON" and inp.applied_cooling != "ON":
        return DoorControlDecision(
            ACTION_ISSUE_ON, "MEMBER_POLICY_COOLING_REQUEST", IDLE,
            "member policy requests cooling while it is not applied")
    if inp.policy_intent == "OFF" and inp.applied_cooling == "ON":
        return DoorControlDecision(
            ACTION_ISSUE_OFF, "MEMBER_POLICY_COOLING_STOP", IDLE,
            "member policy requests stop while cooling is applied")
    return DoorControlDecision(
        ACTION_NONE, "DOOR_CLOSED_NORMAL", IDLE,
        "door closed: member policy satisfied with the applied state")
