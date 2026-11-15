"""W18 safety regressions on disposable PostgreSQL; all inputs are generated.

Some attack fixtures intentionally use live-shaped/PHYSICAL-labelled envelopes
to test the software trust boundary. They are NOT physical acceptance evidence.
MQTT transport in this file is injected, not a real broker or a real actuator.
"""

import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from coldguard_backend import command_publisher as publishing
from coldguard_backend import command_store as commands
from coldguard_backend.command_authorization import CommandAccessDenied
from coldguard_backend.command_publisher import PublishResult
from coldguard_backend.command_service import create_command_intent
from coldguard_backend.controller_b import ControllerBDispatch
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.experiment_store import RunTransition, experiments, transition_run
from coldguard_backend.ingest import ingest_message
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.physical_verification import (
    PhysicalAuthority, PhysicalClaim, PhysicalEvidenceDenied, _check_measurements,
    physical_assessments, record_physical_assessment,
)
from coldguard_backend.raw_store import telemetry_raw
from coldguard_backend.prediction_store import prediction_inputs, record_prediction
from coldguard_backend.twin_store import device_twin, update_derived
from tests.command_testkit import make_ack, make_command, utcnow
from tests.test_command_store import _record_ack
from tests.test_controller_b import SOFTWARE_MODEL, _dispatcher, controller_b_case  # noqa: F401
from tests.test_experiments import run_context  # noqa: F401
from tests.test_twin import _payload
from tests.test_predictions import _draft


def _dispatch(engine, case, transport=None):
    _, command, token, authority, signature = case
    service = _dispatcher(engine, command, token, authority, transport or (lambda *_: PublishResult("PUBACK")))
    return service.dispatch(command, backend_token=token, approval_signature=signature)


def _measurement(engine, command, *, captured=None, received=None, stage="ELECTRICAL_VERIFIED"):
    captured = captured or utcnow()
    received = received or captured
    payload = _payload(
        command.device_id, 2, run_id=command.run_id, captured_at=captured.isoformat(),
        calibration_id="software-calibration", actuation={"cooling": "ON", "duty": 0.5},
    )
    result = ingest_message(
        engine, topic=f"coldguard/{command.device_id}/telemetry", received_at=received,
        payload=json.dumps(payload).encode(),
    )
    with engine.connect() as conn:
        digest = conn.scalar(select(telemetry_raw.c.payload_sha256).where(
            telemetry_raw.c.id == result["raw_id"],
        ))
    claim = PhysicalClaim(
        assessment_id="software-attack-claim", authority_id="software-assessor",
        command_id=command.command_id, device_id=command.device_id, run_id=command.run_id,
        origin="PHYSICAL", stage=stage, reason_code="SOFTWARE_BOUNDARY_TEST_ONLY",
        calibration_id="software-calibration", operating_envelope_id="software-envelope",
        window_start=captured, window_end=captured, assessed_at=utcnow(),
        telemetry_ids=[result["normalized"]["id"]], raw_sha256=[digest],
    )
    return claim, result["raw_id"]


def test_predictive_dispatch_is_disabled_without_approved_model(db_engine, controller_b_case):
    _, command, token, authority, signature = controller_b_case
    sent = []
    service = ControllerBDispatch(
        db_engine, lambda *args: sent.append(args) or PublishResult("PUBACK"),
        transport_ready=lambda: True, backend_token=token,
        allowed_devices=frozenset({command.device_id}), authority=authority,
    )
    with pytest.raises(CommandAccessDenied, match="policy"):
        service.dispatch(command, backend_token=token, approval_signature=signature)
    assert not sent


@pytest.mark.parametrize("writer", ["reported_twin", "run_completion"])
def test_final_context_is_locked_through_transport_handoff(db_engine, controller_b_case, writer):
    _, command, *_ = controller_b_case
    contention = []

    def transport(*_):
        # A separate real database transaction must not invalidate the checked
        # context between the final guard and transport. Bound the test wait.
        try:
            with db_engine.begin() as other:
                other.execute(text("SET LOCAL lock_timeout = '100ms'"))
                if writer == "reported_twin":
                    update_derived(other, command.device_id, {"software_race": True})
                else:
                    transition_run(other, command.run_id, RunTransition(status="COMPLETED_RAW"))
        except DBAPIError as exc:
            contention.append(getattr(exc.orig, "sqlstate", None))
        else:
            contention.append("CONTEXT_CHANGED_BEFORE_SEND")
        return PublishResult("PUBACK")

    assert _dispatch(db_engine, controller_b_case, transport)["outcome"] == "puback"
    assert contention == ["55P03"], "final context was not held through the transport handoff"
    # Locks are transaction-scoped and do not prevent progress afterwards.
    with db_engine.begin() as conn:
        if writer == "reported_twin":
            update_derived(conn, command.device_id, {"software_after_dispatch": True})
        else:
            transition_run(conn, command.run_id, RunTransition(status="COMPLETED_RAW"))


def test_outgoing_payload_must_equal_signed_and_stored_envelope(db_engine, controller_b_case, monkeypatch):
    original = publishing.command_from_row

    def corrupt(row):
        result = original(row)
        return result.model_copy(update={"reason_code": "UNSIGNED_TAMPERING"})

    monkeypatch.setattr(publishing, "command_from_row", corrupt)
    sent = []
    result = _dispatch(
        db_engine, controller_b_case, lambda *args: sent.append(args) or PublishResult("PUBACK"),
    )
    assert result["outcome"] in {"payload_fence_rejected", "policy_fence_rejected"}
    assert not sent


def test_d_approval_receipt_is_durable_before_transport_and_trace_is_repeatable(db_engine, controller_b_case):
    client, command, *_ = controller_b_case
    observed = []
    path = f"/api/runs/{command.run_id}/controller-b-trace"

    def transport(topic, payload, qos, retain):
        observed.append((client.get(path).json()["commands"][0], payload, qos, retain))
        return PublishResult("PUBACK")

    assert _dispatch(db_engine, controller_b_case, transport)["outcome"] == "puback"
    item, payload, qos, retain = observed[0]
    approval = item.get("policy_approval")
    assert approval is not None, "approval disappeared across the crash window before broker handoff"
    assert approval["command_sha256"] == hashlib.sha256(payload).hexdigest()
    assert approval["policy_version"] == command.policy_version
    assert approval["model_spec"]["model_version"] == item["prediction"]["model_version"]
    assert approval["signature_sha256"] and approval["approved_at"]
    assert qos == 1 and retain is False
    first, second = client.get(path, params={"download": True}), client.get(path, params={"download": True})
    assert first.content == second.content


def test_predictive_command_cannot_dispatch_in_reactive_run(db_engine, controller_b_case):
    _, command, *_ = controller_b_case
    with db_engine.begin() as conn:
        conn.execute(experiments.update().where(experiments.c.run_id == command.run_id).values(controller_id="REACTIVE"))
    sent = []
    with pytest.raises(CommandAccessDenied):
        _dispatch(db_engine, controller_b_case, lambda *args: sent.append(args) or PublishResult("PUBACK"))
    assert not sent


def test_old_acquisition_does_not_become_fresh_from_recent_receipt(db_engine, controller_b_case):
    _, command, *_ = controller_b_case
    with db_engine.begin() as conn:
        source = conn.execute(select(telemetry_raw).where(
            telemetry_raw.c.device_id == command.device_id,
        )).mappings().one()
        payload = dict(source["raw_json"])
        captured = utcnow() - timedelta(hours=1)
        payload["captured_at"] = captured.isoformat()
        wire = json.dumps(payload)
        conn.execute(telemetry_raw.update().where(telemetry_raw.c.id == source["id"]).values(
            raw_payload=wire, raw_json=payload, captured_at=captured,
            payload_sha256=hashlib.sha256(wire.encode()).hexdigest(),
        ))
        conn.execute(telemetry.update().where(telemetry.c.raw_id == source["id"]).values(time=captured))
    with pytest.raises(CommandAccessDenied):
        _dispatch(db_engine, controller_b_case)


@pytest.mark.parametrize("change", [
    "exact_bytes", "raw_json", "normalized_content", "raw_identity", "receipt_time", "old_acquisition",
    "hidden_synthetic_marker",
])
def test_physical_measurement_uses_exact_content_and_acquisition_not_projection(db_engine, controller_b_case, change):
    _, command, *_ = controller_b_case
    claim, raw_id = _measurement(db_engine, command)
    with db_engine.begin() as conn:
        raw = conn.execute(select(telemetry_raw).where(telemetry_raw.c.id == raw_id)).mappings().one()
        if change == "exact_bytes":
            conn.execute(telemetry_raw.update().where(telemetry_raw.c.id == raw_id).values(raw_payload=raw["raw_payload"] + " "))
        elif change == "raw_json":
            conn.execute(telemetry_raw.update().where(telemetry_raw.c.id == raw_id).values(raw_json={}))
        elif change == "normalized_content":
            conn.execute(telemetry.update().where(telemetry.c.raw_id == raw_id).values(cooling_power_w=1.0))
        elif change == "raw_identity":
            conn.execute(telemetry_raw.update().where(telemetry_raw.c.id == raw_id).values(boot_id="foreign-boot"))
        elif change == "receipt_time":
            conn.execute(telemetry_raw.update().where(telemetry_raw.c.id == raw_id).values(
                backend_received_at=claim.window_start - timedelta(seconds=1),
            ))
        else:
            payload = dict(raw["raw_json"])
            if change == "old_acquisition":
                payload["captured_at"] = (claim.window_start - timedelta(hours=1)).isoformat()
                conn.execute(telemetry.update().where(telemetry.c.raw_id == raw_id).values(
                    time=claim.window_start - timedelta(hours=1),
                ))
            else:
                payload["synthetic"] = True
            wire = json.dumps(payload)
            digest = hashlib.sha256(wire.encode()).hexdigest()
            conn.execute(telemetry_raw.update().where(telemetry_raw.c.id == raw_id).values(
                raw_payload=wire, payload_sha256=digest,
                raw_json=payload if change == "old_acquisition" else raw["raw_json"],
            ))
            claim = claim.model_copy(update={"raw_sha256": [digest]})
        with pytest.raises(PhysicalEvidenceDenied, match="provenance|acquisition"):
            _check_measurements(conn, claim)
        assert conn.execute(select(physical_assessments.c.assessment_id)).first() is None


def test_delayed_telemetry_remains_usable_for_its_actual_acquisition_window(db_engine, controller_b_case):
    _, command, *_ = controller_b_case
    claim, _ = _measurement(db_engine, command, captured=utcnow() - timedelta(seconds=1), received=utcnow())
    with db_engine.begin() as conn:
        _check_measurements(conn, claim)


def test_executed_is_an_independent_telemetry_assessment_stage(db_engine, controller_b_case):
    _, command, *_ = controller_b_case
    claim, _ = _measurement(db_engine, command, stage="EXECUTED")
    assert claim.stage == commands.EXECUTED


def test_ack_cannot_skip_applied_execution_stage(db_engine, controller_b_case):
    _, command, *_ = controller_b_case
    assert _dispatch(db_engine, controller_b_case)["outcome"] == "puback"
    assert _record_ack(db_engine, make_ack(command.command_id, device_id=command.device_id), topic_device=command.device_id)["status"] == commands.ACK_ACCEPTED
    claim, _ = _measurement(db_engine, command)
    key = b"software-only-assessment-key-32bytes"
    authority = PhysicalAuthority("software-assessor", key, frozenset({"software-envelope"}))
    signature = hmac.digest(key, encode_evidence(claim.model_dump()), "sha256").hex()
    with db_engine.begin() as conn:
        with pytest.raises(PhysicalEvidenceDenied, match="lifecycle state"):
            record_physical_assessment(conn, claim, authority=authority, signature=signature)
        assert commands.get_command(conn, command.command_id)["status"] == commands.ACK_ACCEPTED


@pytest.mark.parametrize("field,value", [
    ("model_version", "unapproved-model"), ("artifact_sha256", "3" * 64),
    ("feature_version", "unapproved-features"), ("feature_schema_sha256", "4" * 64), ("horizon_s", 90),
])
def test_every_frozen_model_provenance_field_is_checked(db_engine, controller_b_case, field, value):
    _, command, token, authority, signature = controller_b_case
    sent = []
    service = ControllerBDispatch(
        db_engine, lambda *args: sent.append(args) or PublishResult("PUBACK"),
        transport_ready=lambda: True, backend_token=token, allowed_devices=frozenset({command.device_id}),
        authority=authority, approved_model=SOFTWARE_MODEL.model_copy(update={field: value}),
    )
    with pytest.raises(CommandAccessDenied):
        service.dispatch(command, backend_token=token, approval_signature=signature)
    assert not sent


@pytest.mark.parametrize("field,value", [
    ("command_id", "unsigned-identity"), ("reason_code", "UNSIGNED_REASON"),
    ("run_id", "unsigned-run"), ("prediction_id", "unsigned-prediction"),
    ("expected_twin_version", 0),
])
def test_d_signature_covers_the_entire_command(db_engine, controller_b_case, field, value):
    _, command, token, authority, signature = controller_b_case
    sent = []
    service = _dispatcher(db_engine, command, token, authority, lambda *args: sent.append(args) or PublishResult("PUBACK"))
    with pytest.raises(CommandAccessDenied):
        service.dispatch(command.model_copy(update={field: value}), backend_token=token, approval_signature=signature)
    assert not sent


@pytest.mark.parametrize("change", ["run_closed", "prediction_replaced", "superseded", "expired"])
def test_reservation_does_not_skip_final_revocation(db_engine, controller_b_case, monkeypatch, change):
    _, command, *_ = controller_b_case
    original = publishing.command_from_row

    def revoke(row):
        if change == "run_closed":
            with db_engine.begin() as conn:
                transition_run(conn, command.run_id, RunTransition(status="COMPLETED_RAW"))
        elif change == "prediction_replaced":
            with db_engine.begin() as conn:
                ids = list(conn.scalars(select(prediction_inputs.c.telemetry_id).where(
                    prediction_inputs.c.prediction_id == command.prediction_id,
                )))
                receipt = conn.scalar(select(telemetry.c.backend_received_at).where(telemetry.c.id == ids[0]))
                record_prediction(conn, _draft(command.device_id, command.run_id, ids, receipt))
        elif change == "superseded":
            create_command_intent(db_engine, make_command("software-new-intent", device_id=command.device_id))
        else:
            class ExpiredClock:
                @staticmethod
                def now(_zone):
                    return command.expires_at + timedelta(microseconds=1)

            monkeypatch.setattr(publishing, "datetime", ExpiredClock)
        return original(row)

    monkeypatch.setattr(publishing, "command_from_row", revoke)
    sent = []
    result = _dispatch(db_engine, controller_b_case, lambda *args: sent.append(args) or PublishResult("PUBACK"))
    expected = "superseded" if change == "superseded" else "expired" if change == "expired" else "policy_fence_rejected"
    assert result["outcome"] == expected
    assert not sent


def _sign_claim(key, claim):
    return hmac.digest(key, encode_evidence(claim.model_dump()), "sha256").hex()


def _accept(engine, case):
    _, command, *_ = case
    assert _dispatch(engine, case)["outcome"] == "puback"
    assert _record_ack(engine, make_ack(
        command.command_id, device_id=command.device_id, boot_id="boot-z",
    ), topic_device=command.device_id)["status"] == commands.ACK_ACCEPTED


def test_software_assessment_chain_and_late_ack_never_shortcut_physical_proof(db_engine, controller_b_case):
    """Exercise signed authority plumbing, NOT real electrical/thermal acceptance."""
    client, command, *_ = controller_b_case
    _accept(db_engine, controller_b_case)
    base, _ = _measurement(db_engine, command, stage="EXECUTED")
    key = b"software-only-assessment-key-32bytes"
    authority = PhysicalAuthority("software-assessor", key, frozenset({"software-envelope"}))
    with db_engine.begin() as conn:
        saved = record_physical_assessment(conn, base, authority=authority, signature=_sign_claim(key, base))
        assert record_physical_assessment(conn, base, authority=authority, signature=_sign_claim(key, base)) == saved
        assert commands.get_command(conn, command.command_id)["status"] == commands.EXECUTED
        electrical = base.model_copy(update={
            "assessment_id": "software-electrical", "stage": commands.ELECTRICAL_VERIFIED, "assessed_at": utcnow(),
        })
        record_physical_assessment(conn, electrical, authority=authority, signature=_sign_claim(key, electrical))
    captured = utcnow()
    sample = _payload(command.device_id, 3, run_id=command.run_id, captured_at=captured.isoformat(),
                      calibration_id="software-calibration", actuation={"cooling": "ON", "duty": 0.5})
    result = ingest_message(db_engine, topic=f"coldguard/{command.device_id}/telemetry",
                            payload=json.dumps(sample).encode(), received_at=captured)
    with db_engine.begin() as conn:
        digest = conn.scalar(select(telemetry_raw.c.payload_sha256).where(telemetry_raw.c.id == result["raw_id"]))
        thermal = base.model_copy(update={
            "assessment_id": "software-thermal", "stage": commands.THERMAL_VERIFIED,
            "window_end": captured, "assessed_at": utcnow(),
            "telemetry_ids": [*base.telemetry_ids, result["normalized"]["id"]],
            "raw_sha256": [*base.raw_sha256, digest],
        })
        record_physical_assessment(conn, thermal, authority=authority, signature=_sign_claim(key, thermal))
        verified = thermal.model_copy(update={
            "assessment_id": "software-final", "stage": commands.VERIFIED, "assessed_at": utcnow(),
        })
        record_physical_assessment(conn, verified, authority=authority, signature=_sign_claim(key, verified))
        assert commands.get_command(conn, command.command_id)["status"] == commands.VERIFIED
        assert list(conn.scalars(select(commands.command_transitions.c.to_status).where(
            commands.command_transitions.c.command_id == command.command_id,
        ).order_by(commands.command_transitions.c.id))) == [
            commands.VALIDATED, commands.PUBLISHED, commands.ACK_ACCEPTED, commands.EXECUTED,
            commands.ELECTRICAL_VERIFIED, commands.THERMAL_VERIFIED, commands.VERIFIED,
        ]
        with pytest.raises(commands.InvalidTransition):
            commands.transition_command(conn, command.command_id, commands.PUBLISHED)
    later_ack = make_ack(command.command_id, device_id=command.device_id, boot_id="boot-z")
    assert _record_ack(db_engine, later_ack, topic_device=command.device_id)["outcome"] == "duplicate"
    trace = client.get(f"/api/runs/{command.run_id}/controller-b-trace").json()["commands"][0]
    assert trace["command"]["status"] == commands.VERIFIED
    assert [row["stage"] for row in trace["physical_assessments"]] == [
        commands.EXECUTED, commands.ELECTRICAL_VERIFIED, commands.THERMAL_VERIFIED, commands.VERIFIED,
    ]


@pytest.mark.parametrize("attack", ["wrong_boot", "wrong_applied", "bad_signature", "synthetic_origin"])
def test_execution_requires_independent_scope_and_applied_evidence(db_engine, controller_b_case, attack):
    _, command, *_ = controller_b_case
    _accept(db_engine, controller_b_case)
    claim, raw_id = _measurement(db_engine, command, stage="EXECUTED")
    key = b"software-only-assessment-key-32bytes"
    authority = PhysicalAuthority("software-assessor", key, frozenset({"software-envelope"}))
    if attack in {"wrong_boot", "wrong_applied"}:
        with db_engine.begin() as conn:
            source = conn.execute(select(telemetry_raw).where(telemetry_raw.c.id == raw_id)).mappings().one()
            payload = dict(source["raw_json"])
            if attack == "wrong_boot":
                payload["boot_id"] = "foreign-boot"
                updates = {"boot_id": "foreign-boot"}
            else:
                payload["actuation"] = {"cooling": "OFF", "duty": 0.0}
                updates = {"applied_cooling": "OFF", "applied_duty": 0.0}
            wire = json.dumps(payload)
            digest = hashlib.sha256(wire.encode()).hexdigest()
            conn.execute(telemetry_raw.update().where(telemetry_raw.c.id == raw_id).values(
                raw_payload=wire, raw_json=payload, payload_sha256=digest,
                **({"boot_id": "foreign-boot"} if attack == "wrong_boot" else {}),
            ))
            conn.execute(telemetry.update().where(telemetry.c.raw_id == raw_id).values(**updates))
            claim = claim.model_copy(update={"raw_sha256": [digest]})
    if attack == "synthetic_origin":
        claim = claim.model_copy(update={"origin": "SOFTWARE_SIMULATION"})
    signature = "0" * 64 if attack == "bad_signature" else _sign_claim(key, claim)
    with db_engine.begin() as conn:
        with pytest.raises(PhysicalEvidenceDenied):
            record_physical_assessment(conn, claim, authority=authority, signature=signature)
        assert commands.get_command(conn, command.command_id)["status"] == commands.ACK_ACCEPTED
