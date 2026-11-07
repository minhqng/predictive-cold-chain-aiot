"""Durable command chronology using backend timestamps."""

from sqlalchemy import case, select
from sqlalchemy.engine import Connection

from coldguard_backend.command_store import (
    DEVICE_VERDICT_STATUS, CommandNotFound, command_acks, get_command,
)


def _duration_ms(start, end):
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds() * 1000


def command_timing(connection: Connection, command_id: str) -> dict:
    command = get_command(connection, command_id)
    if command is None:
        raise CommandNotFound(command_id)
    ack = command_acks.c
    effective_verdict = case(
        (ack.device_status == "DUPLICATE_CANONICAL", ack.canonical_status), else_=ack.device_status,
    )
    verdicts = [verdict for verdict, status in DEVICE_VERDICT_STATUS.items() if status == command["status"]]
    receipt = None
    if verdicts:
        receipt = connection.execute(
            select(ack.id, ack.backend_received_at, ack.ack_time).where(
                ack.command_id == command_id, ack.topic_device_id == command["device_id"],
                ack.payload_device_id == command["device_id"], ack.validity == "VALID",
                effective_verdict.in_(verdicts),
            ).order_by(ack.backend_received_at, ack.id).limit(1)
        ).mappings().first()
    created = command["created_db_at"]
    puback = command["published_at"]
    received = receipt["backend_received_at"] if receipt else None
    return {
        "command_id": command_id,
        "device_id": command["device_id"],
        "run_id": command["run_id"],
        "prediction_id": command["prediction_id"],
        "status": command["status"],
        "created_at": created,
        "broker_puback_recorded_at": puback,
        "device_ack_received_at": received,
        "device_ack_reported_at": receipt["ack_time"] if receipt else None,
        "ack_receipt_id": receipt["id"] if receipt else None,
        "electrical_verified_at": None,
        "thermal_verified_at": None,
        "physical_timing_reason": "NO_TRUSTED_PHYSICAL_EVIDENCE",
        "created_to_puback_ms": _duration_ms(created, puback),
        "created_to_device_ack_ms": _duration_ms(created, received),
        "device_ack_preceded_puback_record": bool(received and puback and received < puback),
        "timing_basis": "backend timestamps",
    }
