"""Recover unresolved command evidence without publishing or inferring device state."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.engine import Connection, Engine

from coldguard_backend import command_store as commands
from coldguard_backend.command_service import current_desired_command_id
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.twin_store import device_twin


def reconcile_command_history(engine: Engine) -> dict:
    """Resolve old pending attempts and expire due intent. This has no transport."""
    with engine.begin() as connection:
        connection.execute(select(func.pg_advisory_xact_lock(func.hashtext("command-recovery"), 0)))
        affected = commands.reconcile_pending_attempts(connection)
        expired = commands.expire_due_commands(connection)
        return {"uncertain_commands": affected, "expired_commands": expired}


def device_recovery_snapshot(connection: Connection, device_id: str) -> dict:
    """Show durable state and receipt chronology without promoting a boot."""
    twin = connection.execute(
        select(device_twin).where(device_twin.c.device_id == device_id),
    ).mappings().one_or_none()
    samples = telemetry.c
    observed = connection.execute(
        select(samples.boot_id, samples.seq, samples.backend_received_at, samples.twin_eligible)
        .where(samples.device_id == device_id)
        .order_by(samples.backend_received_at.desc(), samples.id.desc()).limit(1)
    ).mappings().one_or_none()
    desired_id = current_desired_command_id(connection, device_id)
    desired = commands.get_command(connection, desired_id) if desired_id else None
    if desired is not None and desired["device_id"] != device_id:
        desired = None
    attempt = commands.command_attempts.c
    pending = connection.scalar(
        select(func.count()).select_from(commands.command_attempts).join(
            commands.commands, commands.commands.c.command_id == attempt.command_id,
        ).where(commands.commands.c.device_id == device_id, attempt.outcome == "PENDING")
    )
    ack = commands.command_acks.c
    newest_ack = connection.execute(
        select(ack.id, ack.command_id, ack.device_status, ack.validity, ack.backend_received_at)
        .where(ack.topic_device_id == device_id)
        .order_by(ack.backend_received_at.desc(), ack.id.desc()).limit(1)
    ).mappings().one_or_none()
    now = datetime.now(timezone.utc)
    return {
        "device_id": device_id,
        "reported": dict(twin["reported_state"]) if twin else {},
        "reported_boot_id": twin["last_boot_id"] if twin else None,
        "reported_seq": twin["last_seq"] if twin else None,
        "latest_observation": dict(observed) if observed else None,
        "desired": {
            "command_id": desired["command_id"], "status": desired["status"],
            "expires_at": desired["expires_at"], "expired": desired["expires_at"] < now,
        } if desired else None,
        "pending_attempts": pending,
        "latest_ack_receipt": dict(newest_ack) if newest_ack else None,
    }
