"""W18 migration proofs on an explicitly isolated disposable PostgreSQL DB.

Generated storage fixtures prove preservation and constraints, not D approval
or physical acceptance. No broker, hardware or production database is used.
"""

import hashlib
import json
import os
from datetime import timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import DBAPIError

from coldguard_backend import command_store as cs
from coldguard_backend.command_service import create_command_intent
from coldguard_backend.controller_b import policy_approvals
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.experiment_store import (
    RunCreate, RunTransition, create_run, experiment_transitions, experiments, transition_run,
)
from coldguard_backend.ingest import ingest_message
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.physical_verification import physical_assessments
from coldguard_backend.prediction_store import prediction_inputs, predictions, record_prediction
from coldguard_backend.raw_store import telemetry_raw
from coldguard_backend.shadow_trace import shadow_decisions
from coldguard_backend.twin_store import device_twin
from tests.command_testkit import ack_bytes, cleanup_commands, make_ack, make_command, utcnow
from tests.test_command_migration import ENV, _downgrade, _ensure, _revision, _upgrade, _url
from tests.test_controller_b import SOFTWARE_MODEL
from tests.test_migration_w05 import _cleanup_device
from tests.test_predictions import _draft
from tests.test_twin import _payload

pytestmark = pytest.mark.skipif(
    not os.environ.get(ENV), reason="requires isolated disposable PostgreSQL migration database",
)
NEW_TABLES = {"policy_approvals", "physical_assessments"}
HISTORY = (
    telemetry_raw, telemetry, device_twin, experiments, experiment_transitions,
    predictions, prediction_inputs, shadow_decisions, cs.commands,
    cs.command_attempts, cs.command_acks, cs.command_transitions,
)


@pytest.fixture
def migration_engine():
    engine = create_engine(_url())
    assert engine.url.host in {"127.0.0.1", "localhost", "::1"}
    assert engine.url.database not in {"postgres", "template0", "template1"}
    suite = os.environ.get("COLDGUARD_TEST_DATABASE_URL")
    if suite:
        other = create_engine(suite)
        try:
            assert engine.url != other.url, "migration DB must be separate from the suite DB"
        finally:
            other.dispose()
    try:
        yield engine
    finally:
        engine.dispose()


def _fingerprints(engine, tables=HISTORY):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        result = {}
        for table in tables:
            rows = [dict(row) for row in connection.execute(
                select(table).order_by(*table.primary_key.columns),
            ).mappings()]
            result[table.name] = {"rows": len(rows), "sha256": hashlib.sha256(encode_evidence(rows)).hexdigest()}
        return result


def _seed_history(engine, device, run_id):
    with engine.begin() as connection:
        create_run(connection, RunCreate(
            run_id=run_id, device_id=device, scenario_id="S2", controller_id="REACTIVE",
            pair_id="software-migration-pair", versions={"schema_version": 1},
            notes="Generated migration-preservation fixture; no physical campaign.",
        ))
        for status in ("ARMED", "RUNNING"):
            transition_run(connection, run_id, RunTransition(status=status))
    received = utcnow()
    sample = _payload(device, 1, run_id=run_id, captured_at=received.isoformat())
    row = ingest_message(engine, topic=f"coldguard/{device}/telemetry",
                         payload=json.dumps(sample).encode(), received_at=received)
    draft = _draft(device, run_id, [row["normalized"]["id"]], received)
    with engine.begin() as connection:
        record_prediction(connection, draft)
        shadow = {
            "decision_id": "shadow-" + run_id, "prediction_id": draft.prediction_id,
            "policy_version": "software-policy", "would_command": {"cooling": "ON"},
            "reason_code": "SOFTWARE_ONLY", "reason_detail": "Storage-preservation fixture.",
            "status": "EVALUATED", "feature_names": ["t1", "t2"], "feature_values": [6.0, 8.0],
        }
        connection.execute(shadow_decisions.insert().values(
            **shadow, evaluated_at=utcnow(), policy_duration_ms=1.0,
            payload_sha256=hashlib.sha256(encode_evidence(shadow)).hexdigest(),
        ))
    command = make_command(
        "command-" + run_id, device_id=device, run_id=run_id, prediction_id=draft.prediction_id,
        created_at=utcnow().astimezone(timezone(timedelta(hours=7))),
    )
    create_command_intent(engine, command)
    # Pre-0012 hashes are preserved verbatim, including a legacy non-UTC hash.
    legacy_digest = hashlib.sha256(json.dumps(
        command.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    with engine.begin() as connection:
        connection.execute(cs.commands.update().where(cs.commands.c.command_id == command.command_id).values(
            payload_sha256=legacy_digest,
        ))
        phase = cs.begin_publish_attempt(connection, command.command_id, payload_sha256=legacy_digest)
        cs.finish_publish_attempt(connection, command.command_id, phase["attempt_id"], outcome="PUBACK")
        ack = make_ack(command.command_id, device_id=device, boot_id="boot-z")
        wire = ack_bytes(ack)
        cs.record_ack(connection, topic_device_id=device, raw_payload=wire.decode(),
                      payload_sha256=hashlib.sha256(wire).hexdigest(), backend_received_at=utcnow(),
                      ack=ack, validity="VALID")


def _cleanup_history(engine, device, run_id):
    cleanup_commands(engine, device)
    with engine.begin() as connection:
        ids = select(predictions.c.prediction_id).where(predictions.c.device_id == device)
        connection.execute(shadow_decisions.delete().where(shadow_decisions.c.prediction_id.in_(ids)))
        connection.execute(prediction_inputs.delete().where(prediction_inputs.c.prediction_id.in_(ids)))
        connection.execute(predictions.delete().where(predictions.c.device_id == device))
        connection.execute(experiment_transitions.delete().where(experiment_transitions.c.run_id == run_id))
        connection.execute(experiments.delete().where(experiments.c.run_id == run_id))
    _cleanup_device(engine, device)


def test_0012_empty_upgrade_safe_downgrade_and_reupgrade(migration_engine):
    _ensure("0011", migration_engine)
    before = _fingerprints(migration_engine)
    assert not NEW_TABLES.intersection(inspect(migration_engine).get_table_names())
    _upgrade("0012")
    assert _revision(migration_engine) == "0012"
    assert NEW_TABLES.issubset(inspect(migration_engine).get_table_names())
    checks = {row["name"]: row["sqltext"] for row in inspect(migration_engine).get_check_constraints("commands")}
    assert "EXECUTED" in checks["ck_commands_verification_status"]
    assert _fingerprints(migration_engine) == before
    _downgrade("0011")
    assert _revision(migration_engine) == "0011"
    assert _fingerprints(migration_engine) == before
    _upgrade("0012")
    assert _fingerprints(migration_engine) == before


def test_0012_populated_upgrade_and_rollback_preserve_exact_history(migration_engine, tmp_path):
    _ensure("0011", migration_engine)
    device, run_id = "migration-" + uuid4().hex, "migration-run-" + uuid4().hex
    try:
        _seed_history(migration_engine, device, run_id)
        before = _fingerprints(migration_engine)
        assert all(entry["rows"] for entry in before.values())
        stages = {"before_0012": before}
        for name, operation in (("upgrade", lambda: _upgrade("0012")),
                                ("safe_downgrade", lambda: _downgrade("0011")),
                                ("reupgrade", lambda: _upgrade("0012"))):
            operation()
            stages[name] = _fingerprints(migration_engine)
            assert stages[name] == before
        (tmp_path / "w18-migration-preservation.json").write_bytes(encode_evidence({
            "data_class": "SOFTWARE_SIMULATION", "stages": stages,
            "preserved": "all raw/normalized/Twin/run/prediction/shadow/command/attempt/ACK/transition columns",
        }))
    finally:
        _cleanup_history(migration_engine, device, run_id)


def _new_evidence(connection, command, kind):
    if kind == "execution_state":
        connection.execute(cs.commands.update().where(cs.commands.c.command_id == command.command_id).values(
            status=cs.EXECUTED, verification_status=cs.EXECUTED,
        ))
        return cs.commands
    if kind == "policy_approval":
        spec = SOFTWARE_MODEL.model_dump(mode="json")
        connection.execute(policy_approvals.insert().values(
            command_id=command.command_id, authority_id="software-storage-fixture", policy_version=command.policy_version,
            command_sha256=cs.command_payload_sha256(command), signature_sha256="a" * 64,
            model_spec=spec, model_spec_sha256=hashlib.sha256(encode_evidence(spec)).hexdigest(), approved_at=utcnow(),
        ))
        return policy_approvals
    claim = {"origin": "SOFTWARE_SIMULATION", "note": "Storage constraint fixture, not a physical claim."}
    connection.execute(physical_assessments.insert().values(
        assessment_id=command.command_id, command_id=command.command_id, authority_id="software-storage-fixture",
        stage=cs.EXECUTED, assessed_at=utcnow(), claim=claim,
        claim_sha256=hashlib.sha256(encode_evidence(claim)).hexdigest(), signature_sha256="b" * 64,
    ))
    return physical_assessments


@pytest.mark.parametrize("kind", ["policy_approval", "physical_assessment", "execution_state"])
def test_0012_populated_downgrade_refuses_and_preserves_evidence(migration_engine, kind):
    _ensure("0012", migration_engine)
    command = make_command("migration-evidence-" + uuid4().hex, device_id="software-migration")
    try:
        with migration_engine.begin() as connection:
            cs.create_command(connection, command)
            _new_evidence(connection, command, kind)
        before = _fingerprints(migration_engine, (*HISTORY, policy_approvals, physical_assessments))
        with pytest.raises(DBAPIError, match="revision 0012 downgrade refused"):
            _downgrade("0011")
        assert _revision(migration_engine) == "0012"
        assert _fingerprints(migration_engine, (*HISTORY, policy_approvals, physical_assessments)) == before
    finally:
        with migration_engine.begin() as connection:
            for table in (policy_approvals, physical_assessments):
                connection.execute(table.delete().where(table.c.command_id == command.command_id))
            connection.execute(cs.commands.delete().where(cs.commands.c.command_id == command.command_id))


@pytest.mark.parametrize("kind", ["policy_approval", "physical_assessment"])
def test_0012_evidence_update_is_immutable(migration_engine, kind):
    _ensure("0012", migration_engine)
    command = make_command("migration-immutable-" + uuid4().hex, device_id="software-migration")
    try:
        with migration_engine.begin() as connection:
            cs.create_command(connection, command)
            table = _new_evidence(connection, command, kind)
        before = _fingerprints(migration_engine, (table, cs.commands))
        with pytest.raises(DBAPIError, match="evidence is immutable"):
            with migration_engine.begin() as connection:
                connection.execute(table.update().where(table.c.command_id == command.command_id).values(
                    authority_id="tampered",
                ))
        with pytest.raises(DBAPIError, match="command provenance is immutable"):
            with migration_engine.begin() as connection:
                connection.execute(cs.commands.update().where(cs.commands.c.command_id == command.command_id).values(
                    payload_sha256="c" * 64,
                ))
        assert _fingerprints(migration_engine, (table, cs.commands)) == before
    finally:
        with migration_engine.begin() as connection:
            connection.execute(table.delete().where(table.c.command_id == command.command_id))
            connection.execute(cs.commands.delete().where(cs.commands.c.command_id == command.command_id))
