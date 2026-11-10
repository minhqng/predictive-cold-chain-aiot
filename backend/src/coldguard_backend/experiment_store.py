"""Experiment identity, lifecycle and audit history (C-W07-01/02)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import BigInteger, Column, DateTime, MetaData, Table, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Connection

metadata = MetaData()
experiments = Table(
    "experiments", metadata,
    Column("run_id", Text, primary_key=True),
    Column("device_id", Text),
    Column("scenario_id", Text),
    Column("controller_id", Text),
    Column("pair_id", Text),
    Column("versions", JSONB),
    Column("status", Text),
    Column("notes", Text),
    Column("created_at", DateTime(timezone=True)),
    Column("started_at", DateTime(timezone=True)),
    Column("ended_at", DateTime(timezone=True)),
)
experiment_transitions = Table(
    "experiment_transitions", metadata,
    Column("id", BigInteger, primary_key=True),
    Column("run_id", Text),
    Column("from_status", Text),
    Column("to_status", Text),
    Column("reason", Text),
    Column("occurred_at", DateTime(timezone=True)),
)

RunStatus = Literal[
    "PLANNED", "ARMED", "RUNNING", "COMPLETED_RAW", "VALIDITY_REVIEW",
    "VALID", "INVALID", "ABORTED",
]
Identifier = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^\x00]+$"
)]
DeviceIdentifier = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^/+#\x00]+$"
)]
Reason = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=2000, pattern=r"^[^\x00]+$"
)]

ALLOWED_TRANSITIONS = {
    "PLANNED": {"ARMED", "ABORTED"},
    "ARMED": {"RUNNING", "ABORTED"},
    "RUNNING": {"COMPLETED_RAW", "ABORTED"},
    "COMPLETED_RAW": {"VALIDITY_REVIEW"},
    "VALIDITY_REVIEW": {"VALID", "INVALID", "ABORTED"},
}


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    run_id: Identifier
    device_id: DeviceIdentifier
    scenario_id: Identifier
    controller_id: Identifier
    pair_id: Identifier | None = None
    versions: Annotated[dict[Identifier, Identifier | int | None], Field(min_length=1)]
    notes: Annotated[str, Field(max_length=8000)] | None = None

    @field_validator("run_id")
    @classmethod
    def _addressable_run_id(cls, value: str) -> str:
        if value == "UNSET" or "/" in value or value in {".", ".."}:
            raise ValueError("run_id must be an explicit, addressable identifier")
        return value

    @field_validator("notes")
    @classmethod
    def _valid_notes(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("notes may not contain NUL")
        return value


class RunTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: RunStatus
    reason: Reason | None = None


class RunNotFound(Exception):
    pass


class RunConflict(Exception):
    pass


def get_run(connection: Connection, run_id: str) -> dict:
    row = connection.execute(
        select(experiments).where(experiments.c.run_id == run_id)
    ).mappings().one_or_none()
    if row is None:
        raise RunNotFound(run_id)
    return dict(row)


def create_run(connection: Connection, run: RunCreate) -> dict:
    row = connection.execute(
        insert(experiments).values(
            **run.model_dump(), status="PLANNED", created_at=func.clock_timestamp(),
        ).on_conflict_do_nothing(index_elements=["run_id"]).returning(experiments)
    ).mappings().one_or_none()
    if row is None:
        raise RunConflict(f"run ID {run.run_id!r} is already registered")
    connection.execute(experiment_transitions.insert().values(
        run_id=run.run_id, to_status="PLANNED", occurred_at=row["created_at"],
    ))
    return dict(row)


def transition_run(connection: Connection, run_id: str, change: RunTransition) -> dict:
    """Serialize lifecycle changes and append evidence within the same transaction."""
    current = connection.execute(
        select(experiments).where(experiments.c.run_id == run_id).with_for_update()
    ).mappings().one_or_none()
    if current is None:
        raise RunNotFound(run_id)
    source, target = current["status"], change.status
    if target not in ALLOWED_TRANSITIONS.get(source, ()):
        raise RunConflict(f"run transition {source} -> {target} is not allowed")
    if target in {"VALID", "INVALID", "ABORTED"} and change.reason is None:
        raise RunConflict(f"a recorded reason is required for {target}")
    stamp = connection.scalar(select(func.clock_timestamp()))
    values = {"status": target}
    if target == "RUNNING":
        values["started_at"] = stamp
    if target in {"COMPLETED_RAW", "ABORTED"} and current["ended_at"] is None:
        values["ended_at"] = stamp
    row = connection.execute(
        experiments.update().where(experiments.c.run_id == run_id).values(**values).returning(experiments)
    ).mappings().one()
    connection.execute(experiment_transitions.insert().values(
        run_id=run_id, from_status=source, to_status=target, reason=change.reason,
        occurred_at=stamp,
    ))
    return dict(row)


def run_history(connection: Connection, run_id: str) -> list[dict]:
    return [
        dict(row) for row in connection.execute(
            select(experiment_transitions).where(experiment_transitions.c.run_id == run_id)
            .order_by(experiment_transitions.c.id)
        ).mappings()
    ]
