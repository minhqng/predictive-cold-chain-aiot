"""Immutable prediction provenance and stale-safe derived state."""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, MetaData, Table, Text, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.experiment_store import DeviceIdentifier, Identifier, experiments
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.twin_store import update_derived

metadata = MetaData()
predictions = Table(
    "predictions", metadata,
    Column("prediction_id", Text, primary_key=True),
    Column("device_id", Text),
    Column("run_id", Text),
    Column("model_version", Text),
    Column("model_sha256", Text),
    Column("feature_version", Text),
    Column("feature_schema_sha256", Text),
    Column("risk_score", Float),
    Column("horizon_sec", Integer),
    Column("created_at", DateTime(timezone=True)),
    Column("recorded_at", DateTime(timezone=True)),
    Column("input_window_start", DateTime(timezone=True)),
    Column("input_window_end", DateTime(timezone=True)),
    Column("latest_input_at", DateTime(timezone=True)),
    Column("fresh_until", DateTime(timezone=True)),
    Column("payload_sha256", Text),
)
prediction_inputs = Table(
    "prediction_inputs", metadata,
    Column("prediction_id", Text, primary_key=True),
    Column("ordinal", Integer, primary_key=True),
    Column("telemetry_id", BigInteger),
)

Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
InputId = Annotated[int, Field(gt=0, le=2**63 - 1)]


class PredictionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    prediction_id: Identifier
    device_id: DeviceIdentifier
    run_id: Identifier | None = None
    model_version: Identifier
    model_sha256: Digest
    feature_version: Identifier
    feature_schema_sha256: Digest
    risk_score: Annotated[float, Field(ge=0, le=1)]
    horizon_sec: Annotated[int, Field(gt=0, le=86400)]
    max_input_age_sec: Annotated[int, Field(gt=0, le=86400)]
    created_at: AwareDatetime
    input_window_start: AwareDatetime
    input_window_end: AwareDatetime
    input_telemetry_ids: Annotated[list[InputId], Field(min_length=1, max_length=1000)]

    @field_validator("prediction_id")
    @classmethod
    def _addressable_id(cls, value: str) -> str:
        if "/" in value or value in {".", "..", "current"}:
            raise ValueError("prediction_id must be addressable and cannot be reserved")
        return value

    @model_validator(mode="after")
    def _check_window(self):
        if not self.input_window_start <= self.input_window_end <= self.created_at:
            raise ValueError("prediction input window must precede or end at creation")
        if self.max_input_age_sec > self.horizon_sec:
            raise ValueError("maximum input age cannot exceed the prediction horizon")
        if len(set(self.input_telemetry_ids)) != len(self.input_telemetry_ids):
            raise ValueError("prediction input IDs must be distinct")
        return self


class PredictionConflict(ValueError):
    pass


def _query(device_id: str, run_id: str | None):
    query = select(predictions).where(predictions.c.device_id == device_id)
    if run_id is not None:
        query = query.where(predictions.c.run_id == run_id)
    return query


def _latest(connection: Connection, device_id: str, run_id: str | None = None):
    col = predictions.c
    return connection.execute(
        _query(device_id, run_id).order_by(
            col.latest_input_at.desc(), col.created_at.desc(), col.prediction_id.desc(),
        ).limit(1)
    ).mappings().one_or_none()


def record_prediction(connection: Connection, draft: PredictionDraft) -> dict:
    """Persist checked provenance and update only the derived domain atomically."""
    # Separate lock namespace from command dispatch; only derived writers contend here.
    connection.execute(select(func.pg_advisory_xact_lock(
        func.hashtext("prediction"), func.hashtext(draft.device_id),
    )))
    data = draft.model_dump()
    digest = hashlib.sha256(encode_evidence(data)).hexdigest()
    old = connection.execute(
        select(predictions).where(predictions.c.prediction_id == draft.prediction_id),
    ).mappings().one_or_none()
    if old is not None:
        if old["payload_sha256"] != digest:
            raise PredictionConflict("prediction identity already has different provenance or output")
        return dict(old)
    recorded = connection.scalar(select(func.clock_timestamp()))
    if draft.created_at > recorded:
        raise PredictionConflict("prediction creation cannot be in the future")
    if draft.run_id is not None and connection.scalar(
        select(experiments.c.device_id).where(experiments.c.run_id == draft.run_id)
    ) != draft.device_id:
        raise PredictionConflict("prediction run is unavailable for this device")
    inputs = connection.execute(
        select(telemetry.c.id, telemetry.c.backend_received_at).where(
            telemetry.c.id.in_(draft.input_telemetry_ids), telemetry.c.device_id == draft.device_id,
            telemetry.c.run_id.is_not_distinct_from(draft.run_id),
            telemetry.c.backend_received_at.between(draft.input_window_start, draft.input_window_end),
        )
    ).all()
    if len(inputs) != len(draft.input_telemetry_ids):
        raise PredictionConflict("prediction inputs must exist in the exact device, run and receipt window")
    latest_input = max(row.backend_received_at for row in inputs)
    fresh_until = latest_input + timedelta(seconds=draft.max_input_age_sec)
    del data["input_telemetry_ids"], data["max_input_age_sec"]
    saved = connection.execute(
        insert(predictions).values(
            **data, recorded_at=recorded, latest_input_at=latest_input,
            fresh_until=fresh_until, payload_sha256=digest,
        ).on_conflict_do_nothing(index_elements=["prediction_id"]).returning(predictions)
    ).mappings().one_or_none()
    if saved is None:
        # Another device can race a conflicting globally unique identity.
        raise PredictionConflict("prediction identity already exists")
    connection.execute(prediction_inputs.insert(), [
        {"prediction_id": draft.prediction_id, "ordinal": index, "telemetry_id": telemetry_id}
        for index, telemetry_id in enumerate(draft.input_telemetry_ids)
    ])
    latest = _latest(connection, draft.device_id)
    if latest["prediction_id"] == draft.prediction_id:
        # Keep the same latest evidence in the Twin and current API. Staleness
        # is evaluated at read time, including when a new result arrives stale.
        update_derived(connection, draft.device_id, {
            "prediction": {
                **{key: saved[key] for key in (
                    "prediction_id", "risk_score", "horizon_sec", "model_version", "feature_version",
                )},
                "created_at": saved["created_at"].isoformat(),
                "fresh_until": saved["fresh_until"].isoformat(),
            },
        })
    return dict(saved)


def _status(created: datetime, fresh_until: datetime, now: datetime) -> dict:
    return {
        "prediction_status": "FRESH" if created <= now < fresh_until else "STALE",
        "prediction_age_sec": max(0.0, (now - created).total_seconds()),
    }


def derived_prediction_view(derived: dict, now: datetime) -> dict:
    prediction = derived.get("prediction")
    if not isinstance(prediction, dict) or "fresh_until" not in prediction:
        return derived
    try:
        status = _status(
            datetime.fromisoformat(prediction["created_at"]), datetime.fromisoformat(prediction["fresh_until"]), now,
        )
    except (KeyError, TypeError, ValueError):
        status = {"prediction_status": "UNAVAILABLE", "prediction_age_sec": None}
    view = {**prediction, **status}
    if view["prediction_status"] != "FRESH":
        view["risk_score"] = None
    return {**derived, "prediction": view}


def current_prediction(connection: Connection, device_id: str, run_id: str | None) -> dict:
    row = _latest(connection, device_id, run_id)
    if row is None:
        return {"status": "UNAVAILABLE", "prediction": None}
    status = _status(row["created_at"], row["fresh_until"], datetime.now(timezone.utc))
    item = {**dict(row), **status}
    if status["prediction_status"] == "STALE":
        item["risk_score"] = None
    return {"status": status["prediction_status"], "prediction": item}


def prediction_history(connection: Connection, device_id: str, run_id: str | None, limit: int, offset: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    return [{**dict(row), **_status(row["created_at"], row["fresh_until"], now)} for row in connection.execute(
        _query(device_id, run_id).order_by(
            predictions.c.recorded_at.desc(), predictions.c.prediction_id.desc(),
        ).limit(limit).offset(offset)
    ).mappings()]


def prediction_details(connection: Connection, device_id: str, prediction_id: str) -> dict | None:
    row = connection.execute(
        _query(device_id, None).where(predictions.c.prediction_id == prediction_id)
    ).mappings().one_or_none()
    if row is None:
        return None
    input_ids = connection.scalars(
        select(prediction_inputs.c.telemetry_id).where(prediction_inputs.c.prediction_id == prediction_id)
        .order_by(prediction_inputs.c.ordinal)
    ).all()
    status = _status(row["created_at"], row["fresh_until"], datetime.now(timezone.utc))
    return {**dict(row), **status, "input_telemetry_ids": list(input_ids)}
