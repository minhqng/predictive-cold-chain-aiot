"""Command intent orchestration and desired-Twin linkage (C-W06-05).

Desired state is current valid backend intent; reported state is device
observation; derived state is backend interpretation. These domains are never
collapsed (Doc 05C §16). Creating a command intent:

* persists the durable command (idempotent, conflict-checked);
* links the desired Twin to that command via the existing optimistic
  compare-and-swap (``update_desired``), serialized per device with a
  transaction-level advisory lock so concurrent creators cannot produce an
  inconsistent desired pointer;
* never touches reported state and never marks physical success.

Executable meaning is gated by command status and payload expiry: an expired,
rejected or superseded command is no longer the active desired intent. The
original command and historical desired intent remain auditable; uncertainty
after a network failure is represented (UNKNOWN), never a fabricated OFF/ON.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from coldguard_backend import command_store as cs
from coldguard_backend.contracts import Command
from coldguard_backend.twin_store import device_twin, update_desired

# Statuses whose intent can still have executable meaning (subject to expiry).
EXECUTABLE_STATES = frozenset(
    {cs.CREATED, cs.VALIDATED, cs.PUBLISHED, cs.ACK_ACCEPTED, cs.UNKNOWN}
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def desired_state_for(command: Command) -> dict[str, Any]:
    """The desired-Twin intent document pointing at a command."""
    return {
        "command_id": command.command_id,
        "cooling": command.action.cooling,
        "duty": command.action.duty,
        "expires_at": command.expires_at.isoformat(),
        "controller_id": command.controller_id,
        "policy_version": command.policy_version,
        "reason_code": command.reason_code,
        "intent": "ACTIVE",
    }


def create_command_intent(
    engine: Engine, command: Command, *, now: datetime | None = None
) -> dict[str, Any]:
    """Create a durable command and link it as the device's desired intent.

    The command insert and desired-Twin compare-and-swap share one transaction;
    a per-device advisory lock serializes concurrent intent creators. Returns
    ``{"outcome", "command", "desired_twin_version"}``.
    """
    stamp = now or _utcnow()
    with engine.begin() as connection:
        connection.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(command.device_id)))
        )
        created = cs.create_command(connection, command)
        row = created["command"]
        # If the intent is already past expiry at creation, it has no executable
        # meaning; record it as EXPIRED rather than advertising active intent.
        if row["expires_at"] < stamp and row["status"] not in cs.SETTLED_STATES:
            row = cs.transition_command(
                connection, command.command_id, cs.EXPIRED, reason="expired_at_creation", now=stamp
            )
        twin = connection.execute(
            select(device_twin.c.twin_version).where(
                device_twin.c.device_id == command.device_id
            )
        ).scalar_one_or_none()
        expected_version = int(twin) if twin is not None else 0
        desired = desired_state_for(command)
        if row["status"] == cs.EXPIRED:
            desired["intent"] = "EXPIRED"
        new_version = update_desired(
            connection,
            device_id=command.device_id,
            desired_state=desired,
            expected_version=expected_version,
        )
        connection.execute(
            cs.commands.update().where(cs.commands.c.command_id == command.command_id).values(
                desired_twin_version=new_version
            )
        )
    return {
        "outcome": created["outcome"],
        "command": row,
        "desired_twin_version": new_version,
    }


def active_desired_intent(
    engine: Engine, device_id: str, *, now: datetime | None = None
) -> dict[str, Any] | None:
    """Return the current executable desired intent, or None.

    None when there is no desired command, the command expired, or its status
    lost executable meaning (rejected/superseded/failed). Reported state is
    never consulted or modified here.
    """
    stamp = now or _utcnow()
    with engine.begin() as connection:
        desired = connection.execute(
            select(device_twin.c.desired_state).where(device_twin.c.device_id == device_id)
        ).scalar_one_or_none()
        if not isinstance(desired, dict) or not desired.get("command_id"):
            return None
        command = cs.get_command(connection, desired["command_id"])
        if command is None or command["device_id"] != device_id:
            return None
        if command["status"] not in EXECUTABLE_STATES:
            return None
        if command["expires_at"] < stamp:
            return None
        return {
            "command_id": command["command_id"],
            "cooling": command["action_cooling"],
            "duty": command["action_duty"],
            "expires_at": command["expires_at"].isoformat(),
            "status": command["status"],
        }