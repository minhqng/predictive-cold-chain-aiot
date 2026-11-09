"""Controller B software gates. No physical acceptance or hardware transport."""

import hmac
import json
import secrets
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from coldguard_backend import command_publisher as publishing
from coldguard_backend import command_store as commands
from coldguard_backend.command_authorization import CommandAccessDenied
from coldguard_backend.command_publisher import CommandPublisher, PublishResult
from coldguard_backend.command_service import create_command_intent
from coldguard_backend.controller_b import ControllerBDispatch, DPolicyAuthority, policy_approvals
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.inference import FrozenModelSpec
from coldguard_backend.ingest import ingest_message
from coldguard_backend.physical_verification import (
    PhysicalAuthority, PhysicalClaim, PhysicalEvidenceDenied, physical_assessments, record_physical_assessment,
)
from coldguard_backend.prediction_store import prediction_inputs, predictions, record_prediction
from coldguard_backend.raw_store import telemetry_raw
from coldguard_backend.simulator import build_telemetry
from coldguard_backend.twin_store import device_twin
from tests.command_testkit import cleanup_commands, make_ack, make_command, utcnow
from tests.test_command_store import _record_ack
from tests.test_experiments import run_context  # noqa: F401
from tests.test_predictions import _draft, _sample, prediction_case  # noqa: F401
from tests.test_shadow_trace import shadow_case  # noqa: F401
from tests.test_twin import _payload


SOFTWARE_MODEL = FrozenModelSpec(
    model_version="software-contract-fixture", feature_version="software-features",
    artifact_sha256="1" * 64, feature_schema_sha256="2" * 64,
    feature_names=("t1", "t2"), horizon_s=120,
)


@pytest.fixture
def controller_b_case(db_engine, run_context):
    client, request, _ = run_context
    request.update(controller_id="PREDICTIVE", versions={
        "model_version": SOFTWARE_MODEL.model_version,
        "feature_version": SOFTWARE_MODEL.feature_version,
        "policy_version": "software-d-approval", "schema_version": 1,
    })
    assert client.post("/api/runs", json=request).status_code == 201
    device, run_id = request["device_id"], request["run_id"]
    for status in ("ARMED", "RUNNING"):
        assert client.post(f"/api/runs/{run_id}/transitions", json={"status": status}).status_code == 200
    receipt = utcnow()
    # Fresh live-shaped software envelope, not an actual physical measurement.
    sample = _payload(device, 1, run_id=run_id, captured_at=receipt.isoformat())
    sample_id = ingest_message(
        db_engine, topic=f"coldguard/{device}/telemetry", received_at=receipt,
        payload=json.dumps(sample).encode(),
    )["normalized"]["id"]
    forecast = _draft(device, run_id, [sample_id], receipt)
    with db_engine.begin() as conn:
        record_prediction(conn, forecast)
        version = conn.scalar(select(device_twin.c.twin_version).where(device_twin.c.device_id == device))
    command = make_command(
        "controller-b-software", device_id=device, run_id=run_id, controller_id="PREDICTIVE",
        prediction_id=forecast.prediction_id, policy_version="software-d-approval",
        expected_twin_version=version, ttl_s=15,
    )
    token, d_key = secrets.token_urlsafe(32), secrets.token_bytes(32)
    authority = DPolicyAuthority(command.policy_version, d_key)
    signature = hmac.digest(d_key, commands.canonical_command_bytes(command), "sha256").hex()
    try:
        yield client, command, token, authority, signature
    finally:
        with db_engine.begin() as conn:
            conn.execute(physical_assessments.delete().where(
                physical_assessments.c.command_id == command.command_id,
            ))
            conn.execute(policy_approvals.delete().where(policy_approvals.c.command_id == command.command_id))
        cleanup_commands(db_engine, device)
        with db_engine.begin() as conn:
            ids = select(predictions.c.prediction_id).where(predictions.c.device_id == device)
            conn.execute(prediction_inputs.delete().where(prediction_inputs.c.prediction_id.in_(ids)))
            conn.execute(predictions.delete().where(predictions.c.device_id == device))


def _dispatcher(engine, command, token, authority, transport):
    return ControllerBDispatch(
        engine, transport, transport_ready=lambda: True, backend_token=token,
        allowed_devices=frozenset({command.device_id}), authority=authority,
        approved_model=SOFTWARE_MODEL,
    )


def test_predictive_publish_has_no_generic_or_unsigned_bypass(db_engine, controller_b_case):
    _, command, token, authority, signature = controller_b_case
    sent = []
    transport = lambda *args: sent.append(args) or PublishResult("PUBACK")
    for service, approval in (
        (_dispatcher(db_engine, command, token, None, transport), signature),
        (_dispatcher(db_engine, command, token, authority, transport), None),
        (_dispatcher(db_engine, command, token, authority, transport), "a" * 64),
    ):
        with pytest.raises(CommandAccessDenied, match="policy did not authorize"):
            service.dispatch(command, backend_token=token, approval_signature=approval)
    with db_engine.connect() as conn:
        assert commands.get_command(conn, command.command_id) is None
    create_command_intent(db_engine, command)
    publisher = CommandPublisher(db_engine, transport)
    assert publisher.publish(command.command_id)["outcome"] == "policy_fence_rejected"
    assert publisher.publish(command.command_id, guard=lambda *_: True)["outcome"] == "policy_fence_rejected"
    assert not sent


def test_approved_software_dispatch_trace_and_synthetic_verification_refusal(
    db_engine, controller_b_case, tmp_path,
):
    client, command, token, authority, signature = controller_b_case
    sent = []
    service = _dispatcher(
        db_engine, command, token, authority, lambda *args: sent.append(args) or PublishResult("PUBACK"),
    )
    result = service.dispatch(command, backend_token=token, approval_signature=signature)
    assert result["outcome"] == "puback" and result["status"] == commands.PUBLISHED
    assert service.dispatch(command, backend_token=token, approval_signature=signature)["outcome"] == "not_publishable"
    assert len(sent) == 1
    with pytest.raises(DBAPIError, match="command provenance is immutable"):
        with db_engine.begin() as conn:
            conn.execute(commands.commands.update().where(
                commands.commands.c.command_id == command.command_id,
            ).values(prediction_id="tampered"))
    assert _record_ack(
        db_engine, make_ack(command.command_id, device_id=command.device_id), topic_device=command.device_id,
    )["status"] == commands.ACK_ACCEPTED
    observed = utcnow()
    sample = build_telemetry(
        device_id=command.device_id, boot_id="software-assessment-fixture", seq=2, run_id=command.run_id,
    )
    sample["calibration_id"] = "software-calibration"
    evidence = ingest_message(
        db_engine, topic=f"coldguard/{command.device_id}/telemetry",
        received_at=observed, payload=json.dumps(sample).encode(),
    )
    assessor_key = secrets.token_bytes(32)
    assessor = PhysicalAuthority("software-test-authority", assessor_key, frozenset({"software-envelope"}))
    with db_engine.begin() as conn:
        raw_hash = conn.scalar(select(telemetry_raw.c.payload_sha256).where(
            telemetry_raw.c.id == evidence["raw_id"],
        ))
        claim = PhysicalClaim(
            assessment_id="software-assessment", authority_id="software-test-authority",
            command_id=command.command_id, device_id=command.device_id, run_id=command.run_id,
            origin="SOFTWARE_SIMULATION", stage="EXECUTED",
            reason_code="SOFTWARE_FIXTURE", calibration_id="software-calibration",
            operating_envelope_id="software-envelope", window_start=observed,
            window_end=observed, assessed_at=utcnow(), telemetry_ids=[evidence["normalized"]["id"]],
            raw_sha256=[raw_hash],
        )
        signed = lambda c: hmac.digest(assessor_key, encode_evidence(c.model_dump()), "sha256").hex()
        with pytest.raises(PhysicalEvidenceDenied, match="not provisioned"):
            record_physical_assessment(conn, claim, authority=None, signature=None)
        with pytest.raises(PhysicalEvidenceDenied, match="trusted physical"):
            record_physical_assessment(conn, claim, authority=assessor, signature=signed(claim))
        relabeled = claim.model_copy(update={"origin": "PHYSICAL"})
        with pytest.raises(PhysicalEvidenceDenied, match="provenance failed"):
            record_physical_assessment(conn, relabeled, authority=assessor, signature=signed(relabeled))
        skipped = relabeled.model_copy(update={"stage": "THERMAL_VERIFIED"})
        with pytest.raises(PhysicalEvidenceDenied, match="lifecycle state"):
            record_physical_assessment(conn, skipped, authority=assessor, signature=signed(skipped))
        assert conn.execute(select(physical_assessments.c.assessment_id)).first() is None
        assert commands.get_command(conn, command.command_id)["verification_status"] == "NONE"

    path = f"/api/runs/{command.run_id}/controller-b-trace"
    response = client.get(path, params={"download": True})
    assert response.status_code == 200
    trace = response.json()["commands"][0]
    assert trace["command"]["prediction_id"] == trace["prediction"]["prediction_id"] == command.prediction_id
    assert trace["command"]["policy_version"] == command.policy_version
    assert trace["attempts"][0]["outcome"] == "PUBACK"
    assert trace["acks"][0]["device_status"] == "ACCEPTED"
    assert trace["physical_response_status"] == "UNAVAILABLE"
    assert trace["physical_assessments"] == []
    (tmp_path / "controller-b-software-trace.json").write_bytes(response.content)


def test_ambiguous_predictive_delivery_does_not_retry(db_engine, controller_b_case):
    _, command, token, authority, signature = controller_b_case
    sent = []
    service = _dispatcher(
        db_engine, command, token, authority, lambda *args: sent.append(args) or PublishResult("TIMEOUT"),
    )
    result = service.dispatch(command, backend_token=token, approval_signature=signature)
    assert result["status"] == commands.UNKNOWN
    with pytest.raises(CommandAccessDenied):
        service.dispatch(command, backend_token=token, approval_signature=signature)
    assert len(sent) == 1


def test_new_report_after_reservation_revokes_signed_twin_context(db_engine, controller_b_case, monkeypatch):
    _, command, token, authority, signature = controller_b_case
    sent = []
    original = publishing.command_from_row

    def advance(row):
        _sample(db_engine, command.device_id, command.run_id, 2, utcnow(), live=True)
        return original(row)

    monkeypatch.setattr(publishing, "command_from_row", advance)
    service = _dispatcher(
        db_engine, command, token, authority, lambda *args: sent.append(args) or PublishResult("PUBACK"),
    )
    result = service.dispatch(command, backend_token=token, approval_signature=signature)
    assert result["outcome"] == "policy_fence_rejected"
    assert not sent
