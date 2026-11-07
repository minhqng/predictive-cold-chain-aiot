"""Durable command lifecycle storage and state machine (C-W06-01/04).

The command path never confuses broker delivery, device ACK and physical
actuation. Lifecycle transitions are database-arbitrated (row locks + an
explicit allowed-transition matrix), append-only attempts/ACKs/transitions
preserve audit evidence, and expired commands can never become executable
again. Physical verification states exist in the matrix but W06 software never
advances into them: an ACCEPTED ACK is protocol evidence, not proof of cooling
(Doc 02 §32.2, §33).

Concurrency:
* ``create_command`` is idempotent on ``command_id`` and rejects a conflicting
  payload under the same id (compare ``payload_sha256``);
* every status change locks the command row (``SELECT ... FOR UPDATE``) and
  checks the transition matrix, so concurrent ACK/expiry/publish writers
  serialize and cannot regress a terminal state;
* expiry arbitration is deterministic: under the row lock, a command past
  ``expires_at`` that is not already accepted/rejected becomes EXPIRED and a
  late ACK is retained as evidence without resurrection.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    Table,
    Text,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.engine import Connection

from coldguard_backend.contracts import Command, CommandAck

_METADATA = MetaData()

commands = Table(
    "commands",
    _METADATA,
    Column("command_id", Text, primary_key=True),
    Column("device_id", Text, nullable=False),
    Column("run_id", Text),
    Column("schema_version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("ack_at", DateTime(timezone=True)),
    Column("controller_id", Text, nullable=False),
    Column("policy_version", Text, nullable=False),
    Column("prediction_id", Text),
    Column("reason_code", Text, nullable=False),
    Column("action_cooling", Text, nullable=False),
    Column("action_duty", Float),
    Column("status", Text, nullable=False),
    Column("reject_reason", Text),
    Column("verification_status", Text, nullable=False),
    Column("payload_sha256", Text, nullable=False),
    Column("expected_twin_version", BigInteger),
    Column("desired_twin_version", BigInteger),
    Column("created_db_at", DateTime(timezone=True), nullable=False),
)

command_attempts = Table(
    "command_attempts",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("command_id", Text, nullable=False),
    Column("attempt_no", Integer, nullable=False),
    Column("outcome", Text, nullable=False),
    Column("broker_reason", Text),
    Column("mqtt_mid", Integer),
    Column("payload_sha256", Text, nullable=False),
    Column("attempted_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
)

command_acks = Table(
    "command_acks",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("command_id", Text),
    Column("topic_device_id", Text, nullable=False),
    Column("payload_device_id", Text),
    Column("boot_id", Text),
    Column("ack_seq", BigInteger),
    Column("device_status", Text),
    Column("reason_code", Text),
    Column("applied_cooling", Text),
    Column("applied_duty", Float),
    Column("device_mode", Text),
    Column("uptime_ms", BigInteger),
    Column("ack_time", DateTime(timezone=True)),
    Column("backend_received_at", DateTime(timezone=True), nullable=False),
    Column("raw_payload", Text, nullable=False),
    Column("payload_sha256", Text, nullable=False),
    Column("validity", Text, nullable=False),
    Column("diagnostics", JSONB),
    Column("time_sync_state", Text),
    Column("expiry_evaluable", Boolean),
    Column("output_stage", Text),
    Column("fault_code", Text),
    Column("reapplied", Boolean),
    Column("canonical_status", Text),
    Column("received_db_at", DateTime(timezone=True), nullable=False),
)

command_transitions = Table(
    "command_transitions",
    _METADATA,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("command_id", Text, nullable=False),
    Column("from_status", Text),
    Column("to_status", Text, nullable=False),
    Column("reason", Text),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

# --- Lifecycle states and transition matrix (C-W06-04) ---------------------

CREATED = "CREATED"
VALIDATED = "VALIDATED"
PUBLISHED = "PUBLISHED"
ACK_ACCEPTED = "ACK_ACCEPTED"
ACK_REJECTED = "ACK_REJECTED"
EXPIRED = "EXPIRED"
UNKNOWN = "UNKNOWN"
PUBLISH_FAILED = "PUBLISH_FAILED"
# Reserved physical verification stages — defined, never set by W06 software.
EXECUTED = "EXECUTED"
ELECTRICAL_VERIFIED = "ELECTRICAL_VERIFIED"
THERMAL_VERIFIED = "THERMAL_VERIFIED"
VERIFIED = "VERIFIED"
FAILED_VERIFICATION = "FAILED_VERIFICATION"

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    CREATED: frozenset({VALIDATED, PUBLISHED, EXPIRED, UNKNOWN, PUBLISH_FAILED}),
    VALIDATED: frozenset({PUBLISHED, EXPIRED, UNKNOWN, PUBLISH_FAILED}),
    PUBLISHED: frozenset({ACK_ACCEPTED, ACK_REJECTED, EXPIRED, UNKNOWN}),
    UNKNOWN: frozenset({PUBLISHED, ACK_ACCEPTED, ACK_REJECTED, EXPIRED}),
    PUBLISH_FAILED: frozenset({PUBLISHED, EXPIRED, UNKNOWN}),
    ACK_ACCEPTED: frozenset(
        {EXECUTED, ELECTRICAL_VERIFIED, THERMAL_VERIFIED, VERIFIED, FAILED_VERIFICATION}
    ),
    ACK_REJECTED: frozenset(),
    EXPIRED: frozenset(),
    EXECUTED: frozenset({ELECTRICAL_VERIFIED, FAILED_VERIFICATION}),
    ELECTRICAL_VERIFIED: frozenset({THERMAL_VERIFIED, FAILED_VERIFICATION}),
    THERMAL_VERIFIED: frozenset({VERIFIED, FAILED_VERIFICATION}),
    VERIFIED: frozenset(),
    FAILED_VERIFICATION: frozenset(),
}

# States from which a fresh publish attempt may be made (subject to expiry).
PUBLISHABLE_STATES = frozenset({CREATED, VALIDATED, PUBLISH_FAILED, UNKNOWN})
# States that own a settled device verdict or expiry; ACKs cannot regress them.
SETTLED_STATES = frozenset({ACK_ACCEPTED, ACK_REJECTED, EXPIRED, VERIFIED, FAILED_VERIFICATION})
TERMINAL_STATES = frozenset({ACK_REJECTED, EXPIRED, VERIFIED, FAILED_VERIFICATION})

# Device verdict -> backend lifecycle status.
_VERDICT_TO_STATUS = {
    "ACCEPTED": ACK_ACCEPTED,
    "REJECTED": ACK_REJECTED,
    "SAFETY_BLOCKED": ACK_REJECTED,
    "INVALID_STATE": ACK_REJECTED,
    "OUT_OF_RANGE": ACK_REJECTED,
    "EXPIRED": EXPIRED,
}


class CommandError(Exception):
    """Base command-path error."""


class CommandConflict(CommandError):
    """Same command_id reused with a conflicting payload."""


class InvalidTransition(CommandError):
    """A requested lifecycle transition is not allowed (no regression)."""


class CommandNotFound(CommandError):
    """No command exists for the given identity."""


class PublishInProgress(CommandError):
    """Another publish workflow holds a pending attempt for this command."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical_command_bytes(command: Command) -> bytes:
    """Deterministic envelope bytes used for conflict detection and publishing."""
    return json.dumps(
        command.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def command_payload_sha256(command: Command) -> str:
    return hashlib.sha256(canonical_command_bytes(command)).hexdigest()


def create_command(
    connection: Connection, command: Command, *, status: str = VALIDATED
) -> dict[str, Any]:
    """Persist a validated command idempotently; reject conflicting payload reuse.

    Returns ``{"outcome": "created"|"exists", "command": <row dict>}``. The
    caller owns the transaction. The Command model has already enforced schema,
    duty range and expiry; database CHECKs enforce them again at the boundary.
    """
    if status not in (CREATED, VALIDATED):
        raise ValueError("a new command must start CREATED or VALIDATED")
    sha = command_payload_sha256(command)
    values = {
        "command_id": command.command_id,
        "device_id": command.device_id,
        "run_id": command.run_id,
        "schema_version": command.schema_version,
        "created_at": command.created_at,
        "expires_at": command.expires_at,
        "controller_id": command.controller_id,
        "policy_version": command.policy_version,
        "prediction_id": command.prediction_id,
        "reason_code": command.reason_code,
        "action_cooling": command.action.cooling,
        "action_duty": command.action.duty,
        "status": status,
        "verification_status": "NONE",
        "payload_sha256": sha,
        "expected_twin_version": command.expected_twin_version,
        "created_db_at": func.clock_timestamp(),
    }
    inserted = connection.execute(
        pg_insert(commands).values(**values).on_conflict_do_nothing(
            index_elements=["command_id"]
        ).returning(commands.c.command_id)
    ).scalar_one_or_none()
    if inserted is not None:
        _record_transition(connection, command.command_id, None, status, "created")
        return {"outcome": "created", "command": get_command(connection, command.command_id)}
    existing = get_command(connection, command.command_id)
    if existing is None:  # pragma: no cover - conflict guarantees a row
        raise CommandError("command conflict reported no existing row")
    if existing["payload_sha256"] != sha:
        raise CommandConflict(
            f"command_id {command.command_id!r} already exists with a different payload"
        )
    return {"outcome": "exists", "command": existing}


def get_command(connection: Connection, command_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        select(commands).where(commands.c.command_id == command_id)
    ).mappings().first()
    return dict(row) if row is not None else None


def _lock_command(connection: Connection, command_id: str) -> dict[str, Any]:
    row = connection.execute(
        select(commands).where(commands.c.command_id == command_id).with_for_update()
    ).mappings().first()
    if row is None:
        raise CommandNotFound(f"command {command_id!r} does not exist")
    return dict(row)


def _record_transition(
    connection: Connection,
    command_id: str,
    from_status: str | None,
    to_status: str,
    reason: str | None,
) -> None:
    connection.execute(
        command_transitions.insert().values(
            command_id=command_id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            occurred_at=func.clock_timestamp(),
        )
    )


def transition_command(
    connection: Connection,
    command_id: str,
    to_status: str,
    *,
    reason: str | None = None,
    expected_from: set[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compare-and-swap a command status under a row lock; forbid regressions."""
    current = _lock_command(connection, command_id)
    from_status = current["status"]
    if expected_from is not None and from_status not in expected_from:
        raise InvalidTransition(
            f"command {command_id!r} is {from_status}, expected one of {sorted(expected_from)}"
        )
    if to_status not in ALLOWED_TRANSITIONS.get(from_status, frozenset()):
        raise InvalidTransition(
            f"transition {from_status} -> {to_status} is not allowed for {command_id!r}"
        )
    stamp = now or _utcnow()
    values: dict[str, Any] = {"status": to_status}
    if to_status == PUBLISHED:
        values["published_at"] = stamp
    if to_status in (ACK_ACCEPTED, ACK_REJECTED):
        values["ack_at"] = stamp
    if to_status == ACK_REJECTED:
        values["reject_reason"] = reason
    connection.execute(
        commands.update().where(commands.c.command_id == command_id).values(**values)
    )
    _record_transition(connection, command_id, from_status, to_status, reason)
    return get_command(connection, command_id)


def next_attempt_no(connection: Connection, command_id: str) -> int:
    current = connection.execute(
        select(func.coalesce(func.max(command_attempts.c.attempt_no), 0)).where(
            command_attempts.c.command_id == command_id
        )
    ).scalar_one()
    return int(current) + 1


def pending_attempt(connection: Connection, command_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        select(command_attempts).where(
            command_attempts.c.command_id == command_id,
            command_attempts.c.outcome == "PENDING",
        ).order_by(command_attempts.c.attempt_no.desc())
    ).mappings().first()
    return dict(row) if row is not None else None


def record_attempt(
    connection: Connection,
    command_id: str,
    *,
    payload_sha256: str,
    outcome: str = "PENDING",
    attempt_no: int | None = None,
    broker_reason: str | None = None,
    mqtt_mid: int | None = None,
) -> dict[str, Any]:
    no = attempt_no if attempt_no is not None else next_attempt_no(connection, command_id)
    attempt_id = connection.execute(
        command_attempts.insert().values(
            command_id=command_id,
            attempt_no=no,
            outcome=outcome,
            broker_reason=broker_reason,
            mqtt_mid=mqtt_mid,
            payload_sha256=payload_sha256,
            attempted_at=func.clock_timestamp(),
        ).returning(command_attempts.c.id)
    ).scalar_one()
    return get_attempt(connection, attempt_id)


def get_attempt(connection: Connection, attempt_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        select(command_attempts).where(command_attempts.c.id == attempt_id)
    ).mappings().first()
    return dict(row) if row is not None else None


def complete_attempt(
    connection: Connection,
    attempt_id: int,
    *,
    outcome: str,
    broker_reason: str | None = None,
    mqtt_mid: int | None = None,
) -> dict[str, Any]:
    connection.execute(
        command_attempts.update().where(command_attempts.c.id == attempt_id).values(
            outcome=outcome,
            broker_reason=broker_reason,
            mqtt_mid=mqtt_mid,
            completed_at=func.clock_timestamp(),
        )
    )
    return get_attempt(connection, attempt_id)


def expire_due_commands(connection: Connection, *, now: datetime | None = None) -> list[str]:
    """Transition every non-settled command past expiry to EXPIRED.

    Used by reconciliation/restart recovery; never re-executes anything. Each
    transition is individually locked and matrix-checked.
    """
    stamp = now or _utcnow()
    due = connection.execute(
        select(commands.c.command_id).where(
            commands.c.expires_at < stamp,
            commands.c.status.not_in(tuple(SETTLED_STATES)),
        )
    ).scalars().all()
    expired: list[str] = []
    for command_id in due:
        current = _lock_command(connection, command_id)
        if current["status"] in SETTLED_STATES:
            continue
        if current["expires_at"] >= stamp:
            continue
        transition_command(connection, command_id, EXPIRED, reason="expiry", now=stamp)
        expired.append(command_id)
    return expired


def _effective_verdict(ack: CommandAck) -> str:
    if ack.status == "DUPLICATE_CANONICAL":
        return ack.canonical_status or "ACCEPTED"
    return ack.status


def record_ack(
    connection: Connection,
    *,
    topic_device_id: str,
    raw_payload: str,
    payload_sha256: str,
    backend_received_at: datetime,
    ack: CommandAck | None,
    validity: str,
    diagnostics: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist ACK receipt evidence and (iff VALID) correlate + transition.

    Evidence is always appended, including unmatched/invalid/conflicting ACKs.
    A VALID ACK is correlated by command_id under a row lock; expiry arbitration
    is deterministic and a late ACK never resurrects an expired command. A
    duplicate ACK produces no second effective transition; a conflicting ACK is
    retained as evidence without overwriting a settled verdict.
    """
    stamp = now or _utcnow()
    fields: dict[str, Any] = {
        "command_id": ack.command_id if ack else None,
        "topic_device_id": topic_device_id,
        "payload_device_id": ack.device_id if ack else None,
        "boot_id": ack.boot_id if ack else None,
        "ack_seq": ack.ack_seq if ack else None,
        "device_status": ack.status if ack else None,
        "reason_code": ack.reason_code if ack else None,
        "applied_cooling": ack.applied.cooling if ack and ack.applied else None,
        "applied_duty": ack.applied.duty if ack and ack.applied else None,
        "device_mode": ack.device_mode if ack else None,
        "uptime_ms": ack.uptime_ms if ack else None,
        "ack_time": ack.ack_time if ack else None,
        "backend_received_at": backend_received_at,
        "raw_payload": raw_payload,
        "payload_sha256": payload_sha256,
        "validity": validity,
        "diagnostics": diagnostics,
        "time_sync_state": ack.time_sync_state if ack else None,
        "expiry_evaluable": ack.expiry_evaluable if ack else None,
        "output_stage": ack.output_stage if ack else None,
        "fault_code": ack.fault_code if ack else None,
        "reapplied": ack.reapplied if ack else None,
        "canonical_status": ack.canonical_status if ack else None,
        "received_db_at": func.clock_timestamp(),
    }
    ack_id = connection.execute(
        command_acks.insert().values(**fields).returning(command_acks.c.id)
    ).scalar_one()

    def _result(outcome: str, **extra) -> dict[str, Any]:
        return {"outcome": outcome, "ack_id": ack_id, **extra}

    if validity != "VALID" or ack is None:
        return _result(validity.lower())

    command = get_command(connection, ack.command_id)
    if command is None:
        connection.execute(
            command_acks.update().where(command_acks.c.id == ack_id).values(validity="UNMATCHED")
        )
        return _result("unmatched")
    if command["device_id"] != ack.device_id:
        connection.execute(
            command_acks.update().where(command_acks.c.id == ack_id).values(
                validity="CONFLICT",
                diagnostics={"code": "ACK_DEVICE_MISMATCH",
                             "command_device": command["device_id"],
                             "ack_device": ack.device_id},
            )
        )
        return _result("conflict")

    locked = _lock_command(connection, ack.command_id)
    verdict = _effective_verdict(ack)
    target = _VERDICT_TO_STATUS.get(verdict)
    if target is None:
        connection.execute(
            command_acks.update().where(command_acks.c.id == ack_id).values(
                validity="CONFLICT",
                diagnostics={"code": "UNMAPPED_VERDICT", "verdict": verdict},
            )
        )
        return _result("conflict")

    # Deterministic expiry arbitration: a command past expiry that has not
    # already settled a verdict becomes EXPIRED; the late ACK is evidence only.
    if locked["expires_at"] < stamp and locked["status"] not in (ACK_ACCEPTED, ACK_REJECTED):
        if locked["status"] != EXPIRED:
            transition_command(connection, ack.command_id, EXPIRED, reason="expiry_before_ack", now=stamp)
        connection.execute(
            command_acks.update().where(command_acks.c.id == ack_id).values(validity="LATE")
        )
        return _result("late_expired", status=EXPIRED)

    if locked["status"] in SETTLED_STATES:
        already = locked["status"]
        if already == target:
            connection.execute(
                command_acks.update().where(command_acks.c.id == ack_id).values(validity="DUPLICATE")
            )
            return _result("duplicate", status=already)
        connection.execute(
            command_acks.update().where(command_acks.c.id == ack_id).values(
                validity="CONFLICT",
                diagnostics={"code": "SETTLED_VERDICT_DIFFERS",
                             "settled": already, "incoming": target},
            )
        )
        return _result("conflict", status=already)

    new = transition_command(connection, ack.command_id, target, reason=ack.reason_code, now=stamp)
    return _result("applied", status=new["status"])


def begin_publish_attempt(
    connection: Connection,
    command_id: str,
    *,
    payload_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Phase 1 of a publish workflow: fence, expiry-check and record PENDING.

    Locks the command row, refuses expired commands (transitioning them to
    EXPIRED), refuses non-publishable states, and fences concurrent publishers
    via an existing PENDING attempt. Returns ``{"outcome": "ready",
    "attempt_id", "command"}`` or ``{"outcome": "expired"|"not_publishable"}``.
    The caller owns the transaction; the MQTT publish happens after commit.
    """
    stamp = now or _utcnow()
    row = _lock_command(connection, command_id)
    if row["expires_at"] < stamp:
        if row["status"] not in SETTLED_STATES:
            transition_command(connection, command_id, EXPIRED, reason="expiry_before_publish", now=stamp)
        return {"outcome": "expired", "command": get_command(connection, command_id)}
    if row["status"] not in PUBLISHABLE_STATES:
        return {"outcome": "not_publishable", "command": row}
    if pending_attempt(connection, command_id) is not None:
        raise PublishInProgress(f"command {command_id!r} already has a pending publish attempt")
    attempt = record_attempt(connection, command_id, payload_sha256=payload_sha256, outcome="PENDING")
    return {"outcome": "ready", "attempt_id": attempt["id"], "command": row}


def finish_publish_attempt(
    connection: Connection,
    command_id: str,
    attempt_id: int,
    *,
    outcome: str,
    broker_reason: str | None = None,
    mqtt_mid: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Phase 3 of a publish workflow: record the broker outcome durably.

    PUBACK advances the command to PUBLISHED (broker delivery only — never
    ACK_ACCEPTED). A definite failure marks PUBLISH_FAILED; a timeout or
    ambiguous outcome marks UNKNOWN (the device may or may not have applied it).
    A verdict that settled while publishing is never regressed.
    """
    stamp = now or _utcnow()
    complete_attempt(connection, attempt_id, outcome=outcome, broker_reason=broker_reason, mqtt_mid=mqtt_mid)
    row = _lock_command(connection, command_id)
    if row["status"] in SETTLED_STATES:
        return row
    if row["status"] not in PUBLISHABLE_STATES:
        return row
    if outcome == "PUBACK":
        return transition_command(connection, command_id, PUBLISHED, reason="broker_puback", now=stamp)
    if outcome == "FAILED":
        return transition_command(connection, command_id, PUBLISH_FAILED, reason=broker_reason, now=stamp)
    return transition_command(connection, command_id, UNKNOWN, reason=broker_reason or "publish_uncertain", now=stamp)


def reconcile_pending_attempts(connection: Connection, *, now: datetime | None = None) -> list[str]:
    """Resolve crash-window PENDING attempts to UNKNOWN without auto-replay.

    A PENDING attempt with no completed outcome means the process crashed after
    fencing but before recording the broker result; the device may or may not
    have received the command. Such commands become UNKNOWN (explicit
    uncertainty) and are never automatically resent. Returns affected ids.
    """
    stamp = now or _utcnow()
    pending = connection.execute(
        select(command_attempts.c.command_id, command_attempts.c.id).where(
            command_attempts.c.outcome == "PENDING"
        )
    ).all()
    affected: list[str] = []
    for command_id, attempt_id in pending:
        complete_attempt(connection, attempt_id, outcome="UNKNOWN", broker_reason="crash_window_unresolved")
        row = get_command(connection, command_id)
        if row is None or row["status"] in SETTLED_STATES:
            continue
        if row["status"] in PUBLISHABLE_STATES:
            transition_command(connection, command_id, UNKNOWN, reason="crash_window_unresolved", now=stamp)
            affected.append(command_id)
    return affected


def list_commands(
    connection: Connection, *, device_id: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    stmt = select(commands)
    if device_id is not None:
        stmt = stmt.where(commands.c.device_id == device_id)
    if status is not None:
        stmt = stmt.where(commands.c.status == status)
    stmt = stmt.order_by(commands.c.created_db_at, commands.c.command_id)
    return [dict(r) for r in connection.execute(stmt).mappings().all()]