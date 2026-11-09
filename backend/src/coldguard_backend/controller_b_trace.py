"""Export Controller B evidence without promoting any physical claim."""

from sqlalchemy import select
from sqlalchemy.engine import Connection

from coldguard_backend import command_store as cs
from coldguard_backend.controller_b import policy_approvals
from coldguard_backend.physical_verification import physical_assessments
from coldguard_backend.prediction_store import prediction_details


def controller_b_trace(connection: Connection, run: dict, *, limit: int, offset: int) -> dict:
    device, run_id = run["device_id"], run["run_id"]
    command_rows = connection.execute(
        select(cs.commands).where(
            cs.commands.c.device_id == device, cs.commands.c.run_id == run_id,
            cs.commands.c.controller_id == "PREDICTIVE",
        ).order_by(cs.commands.c.created_db_at, cs.commands.c.command_id).limit(limit).offset(offset)
    ).mappings().all()
    result = []
    for command in command_rows:
        command_id = command["command_id"]

        def evidence(table, *order, scope=()):
            return [dict(row) for row in connection.execute(
                select(table).where(table.c.command_id == command_id, *scope).order_by(*order)
            ).mappings()]

        assessments = evidence(physical_assessments, physical_assessments.c.assessed_at, physical_assessments.c.assessment_id)
        prediction = prediction_details(connection, device, command["prediction_id"]) if command["prediction_id"] else None
        if prediction is not None and prediction["run_id"] != run_id:
            prediction = None
        if prediction is not None:
            prediction = {key: value for key, value in prediction.items() if key not in (
                "prediction_age_sec", "prediction_status",
            )}
        result.append({
            "command": dict(command), "prediction": prediction,
            "policy_approval": next(iter(evidence(policy_approvals, policy_approvals.c.approved_at)), None),
            "attempts": evidence(cs.command_attempts, cs.command_attempts.c.attempt_no),
            "transitions": evidence(cs.command_transitions, cs.command_transitions.c.id),
            "acks": evidence(
                cs.command_acks, cs.command_acks.c.backend_received_at, cs.command_acks.c.id,
                scope=(cs.command_acks.c.topic_device_id == device, cs.command_acks.c.payload_device_id == device),
            ),
            "physical_assessments": assessments,
            "physical_response_status": "ASSESSMENT_RECORDED" if assessments else "UNAVAILABLE",
        })
    return {
        "format": "coldguard-controller-b-trace-v1",
        "run_id": run_id, "device_id": device, "limit": limit, "offset": offset, "commands": result,
    }
