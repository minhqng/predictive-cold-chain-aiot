"""Online inference and hypothetical policy audit, with no command transport."""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from time import monotonic
from typing import Annotated, Callable, Mapping

from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import Column, DateTime, Float, MetaData, Table, Text, or_, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Connection, Engine

from coldguard_backend.command_store import commands
from coldguard_backend.contracts import CommandAction
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.experiment_store import Identifier, get_run
from coldguard_backend.inference import FrozenModel, InferenceUnavailable, infer_and_record
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.observability import record_event
from coldguard_backend.prediction_store import prediction_inputs, predictions
from coldguard_backend.twin_store import device_twin

log = logging.getLogger(__name__)
shadow_decisions = Table(
    "shadow_decisions", MetaData(),
    Column("decision_id", Text, primary_key=True),
    Column("prediction_id", Text),
    Column("policy_version", Text),
    Column("would_command", JSONB(none_as_null=True)),
    Column("reason_code", Text),
    Column("reason_detail", Text),
    Column("status", Text),
    Column("feature_names", JSONB),
    Column("feature_values", JSONB),
    Column("evaluated_at", DateTime(timezone=True)),
    Column("policy_duration_ms", Float),
    Column("payload_sha256", Text),
)


class ShadowVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    policy_version: Identifier
    would_command: CommandAction | None
    reason_code: Identifier | None
    reason_detail: Annotated[str, StringConstraints(max_length=2000, pattern=r"^[^\x00]*$")]

    @classmethod
    def from_policy_decision(cls, decision) -> "ShadowVerdict":
        """Adapt the existing Member D pure PolicyDecision contract."""
        intent = decision.actuation_intent.value
        return cls(
            policy_version=decision.policy_version,
            would_command=None if intent == "HOLD" else CommandAction(cooling=intent),
            reason_code=decision.reason_code.value if decision.reason_code is not None else None,
            reason_detail=decision.reason_detail,
        )


@dataclass(frozen=True)
class OnlineFeatureAdapter:
    feature_version: str
    feature_schema_sha256: str
    build: Callable[[list[dict]], Mapping[str, float]]


def _online_samples(connection: Connection, run: dict, start: datetime, end: datetime) -> list[dict]:
    device = run["device_id"]
    boot = select(device_twin.c.last_boot_id).where(device_twin.c.device_id == device).scalar_subquery()
    rows = connection.execute(
        select(telemetry).where(
            telemetry.c.device_id == device, telemetry.c.run_id == run["run_id"],
            telemetry.c.boot_id == boot, telemetry.c.twin_eligible,
            telemetry.c.backend_received_at.between(start, end),
        ).order_by(telemetry.c.backend_received_at, telemetry.c.id).limit(1001)
    ).mappings().all()
    if not 1 <= len(rows) <= 1000:
        raise InferenceUnavailable("online window has no eligible samples or exceeds 1000 rows")
    return [dict(row) for row in rows]


def _existing_shadow(connection: Connection, decision_id: str, prediction_id: str):
    return connection.execute(select(shadow_decisions).where(or_(
        shadow_decisions.c.decision_id == decision_id,
        shadow_decisions.c.prediction_id == prediction_id,
    ))).mappings().first()


def run_shadow(
    engine: Engine, *, run_id: str, decision_id: str, prediction_id: str,
    model: FrozenModel, feature_adapter: OnlineFeatureAdapter,
    policy_version: str, evaluate_policy: Callable[[dict, list[dict]], ShadowVerdict],
    input_window_start: datetime, input_window_end: datetime, created_at: datetime,
    max_input_age_sec: int,
) -> dict:
    if not decision_id.strip() or len(decision_id) > 200 or "\x00" in decision_id:
        raise InferenceUnavailable("invalid shadow decision identity")
    spec = model.spec
    if (feature_adapter.feature_version, feature_adapter.feature_schema_sha256) != (
        spec.feature_version, spec.feature_schema_sha256,
    ):
        raise InferenceUnavailable("online feature adapter is not approved for this model")
    if any(value.utcoffset() is None for value in (input_window_start, input_window_end, created_at)):
        raise InferenceUnavailable("shadow window must have timezone-aware timestamps")
    if not input_window_start <= input_window_end <= created_at <= datetime.now(timezone.utc):
        raise InferenceUnavailable("shadow inputs must be past-only")
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        run = get_run(connection, run_id)
        if run["status"] != "RUNNING":
            raise InferenceUnavailable("online shadow evaluation requires a running experiment")
        samples = _online_samples(connection, run, input_window_start, input_window_end)
    device = run["device_id"]
    features = feature_adapter.build(samples)
    result = infer_and_record(
        engine, model, prediction_id=prediction_id, device_id=device, run_id=run_id,
        features=features, input_ids=[row["id"] for row in samples], input_window_start=input_window_start,
        input_window_end=input_window_end, created_at=created_at, max_input_age_sec=max_input_age_sec,
    )
    names, values = list(features), list(features.values())
    with engine.connect() as connection:
        existing = _existing_shadow(connection, decision_id, prediction_id)
    if existing is not None:
        if (
            existing["decision_id"] != decision_id or existing["prediction_id"] != prediction_id
            or existing["policy_version"] != policy_version or existing["feature_names"] != names
            or existing["feature_values"] != values
        ):
            raise InferenceUnavailable("shadow identity already has different evidence")
        return dict(existing)
    started = monotonic()
    if result["status"] == "FRESH":
        verdict = evaluate_policy(result, samples)
        if verdict.policy_version != policy_version:
            raise InferenceUnavailable("shadow policy version is not approved")
        status = "EVALUATED"
    else:
        verdict = ShadowVerdict(
            policy_version=policy_version, would_command=None, reason_code="STALE_PREDICTION",
            reason_detail="Prediction was stale or superseded before shadow evaluation.",
        )
        status = "SKIPPED_STALE"
    data = {
        **verdict.model_dump(mode="json"),
        "decision_id": decision_id, "prediction_id": prediction_id, "status": status,
        "feature_names": names, "feature_values": values,
    }
    digest = hashlib.sha256(encode_evidence(data)).hexdigest()
    with engine.begin() as connection:
        row = connection.execute(
            insert(shadow_decisions).values(
                **data, payload_sha256=digest, evaluated_at=datetime.now(timezone.utc),
                policy_duration_ms=(monotonic() - started) * 1000,
            ).on_conflict_do_nothing().returning(shadow_decisions)
        ).mappings().one_or_none()
        if row is None:
            row = _existing_shadow(connection, decision_id, prediction_id)
            if row is None or row["payload_sha256"] != digest:
                raise InferenceUnavailable("shadow identity already has different evidence")
        saved = dict(row)
    record_event(
        log, "shadow_policy", status.lower(), started, level=logging.INFO,
        device_id=device, run_id=run_id, prediction_id=prediction_id, event_id=decision_id,
    )
    return saved


def shadow_trace(connection: Connection, run: dict, *, limit: int, offset: int) -> dict:
    device, run_id = run["device_id"], run["run_id"]
    pred, decision = predictions.c, shadow_decisions.c
    query = select(predictions, *[
        column.label(f"shadow_{column.name}") for column in shadow_decisions.c
    ]).join_from(predictions, shadow_decisions, pred.prediction_id == decision.prediction_id, isouter=True)
    rows = connection.execute(
        query.where(pred.device_id == device, pred.run_id == run_id)
        .order_by(pred.recorded_at, pred.prediction_id).limit(limit).offset(offset)
    ).mappings().all()
    inputs = {}
    if rows:
        for prediction_id, telemetry_id in connection.execute(
            select(prediction_inputs.c.prediction_id, prediction_inputs.c.telemetry_id)
            .where(prediction_inputs.c.prediction_id.in_([row["prediction_id"] for row in rows]))
            .order_by(prediction_inputs.c.prediction_id, prediction_inputs.c.ordinal)
        ):
            inputs.setdefault(prediction_id, []).append(telemetry_id)
    commands_a = connection.execute(
        select(commands).where(
            commands.c.device_id == device, commands.c.run_id == run_id, commands.c.controller_id == "REACTIVE",
        ).order_by(commands.c.created_db_at, commands.c.command_id).limit(limit).offset(offset)
    ).mappings()
    return {
        "run_id": run_id, "device_id": device, "limit": limit, "offset": offset,
        "predictions": [{
            "prediction": {column.name: row[column.name] for column in predictions.c},
            "input_telemetry_ids": inputs.get(row["prediction_id"], []),
            "shadow_policy": {
                column.name: row[f"shadow_{column.name}"] for column in shadow_decisions.c
            } if row["shadow_decision_id"] is not None else None,
        } for row in rows],
        "controller_a_commands": [dict(row) for row in commands_a],
        "physical_response": {"status": "UNAVAILABLE", "reason": "NO_TRUSTED_PHYSICAL_EVIDENCE"},
    }


def render_shadow_audit(trace: dict) -> str:
    """Render a read-only view of recorded inference and hypothetical policy timing."""
    rows = []
    for item in trace["predictions"]:
        prediction = item["prediction"]
        policy = item["shadow_policy"] or {}
        values = (
            prediction["prediction_id"], prediction["created_at"].isoformat(),
            prediction["recorded_at"].isoformat(),
            policy["evaluated_at"].isoformat() if policy else "Unavailable",
            policy.get("policy_duration_ms", "Unavailable"),
            policy.get("status", "No decision"),
        )
        cells = "".join(f"<td>{escape(str(value))}</td>" for value in values)
        rows.append(f"<tr>{cells}</tr>")
    if not rows:
        rows.append('<tr><td colspan="6">No recorded predictions</td></tr>')
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Shadow policy audit</title></head><body><main>'
        f'<h1>Shadow policy audit for {escape(trace["run_id"])}</h1>'
        '<p>Policy decisions are hypothetical. Physical response evidence is unavailable.</p>'
        '<table><caption>Prediction and policy timing</caption><thead><tr>'
        '<th scope="col">Prediction</th><th scope="col">Prediction created</th>'
        '<th scope="col">Prediction recorded</th><th scope="col">Policy evaluated</th>'
        '<th scope="col">Policy duration (ms)</th><th scope="col">Policy status</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></main></body></html>'
    )
