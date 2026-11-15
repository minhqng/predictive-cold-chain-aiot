"""Populated preservation fixtures. SOFTWARE_SIMULATION, never official approval."""

import json
import os
from datetime import timedelta
from pathlib import Path
from time import monotonic
from uuid import uuid4

from sqlalchemy import select

from coldguard_backend import command_store as cs
from coldguard_backend.campaign_freeze import FreezeDraft
from coldguard_backend.campaign_integrity import close_run
from coldguard_backend.controller_b import policy_approvals
from coldguard_backend.evidence_backup import backup_campaign, local_database_url
from coldguard_backend.evidence_package import digest
from coldguard_backend.evidence_tables import fingerprint_connection
from coldguard_backend.experiment_evidence import encode_evidence
from coldguard_backend.inference import FrozenModelSpec
from coldguard_backend.normalized_store import telemetry
from coldguard_backend.physical_verification import PhysicalClaim, physical_assessments
from coldguard_backend.prediction_store import PredictionDraft, record_prediction
from coldguard_backend.raw_store import store_raw
from coldguard_backend.reconciliation import reconciliation_legacy_audit
from coldguard_backend.shadow_trace import ShadowVerdict, shadow_decisions
from coldguard_backend.twin_store import _retired_boot
from coldguard_backend.command_service import create_command_intent
from tests.campaign_testkit import campaign_draft, complete_run, register_fixture, snapshot_transaction
from tests.command_testkit import ack_bytes, make_ack, make_command, utcnow
from coldguard_backend.simulator import build_telemetry


def populated_context(engine, directory: Path, *, backend_commit: str) -> dict:
    """Require a freshly migrated owned DB; keep every generated/failed fixture."""
    local_database_url(engine.url)
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        inventory = fingerprint_connection(connection)
    if inventory["revisions"] != ["0014"] or any(row["rows"] for name, row in inventory["tables"].items()
                                               if name not in {"alembic_version", "reconciliation_boundary"}):
        raise ValueError("populated handover fixture requires a fresh empty migrated source")
    directory.mkdir(parents=True, exist_ok=False)
    draft = campaign_draft()
    for plan in draft["runs"]:
        plan["run"]["versions"]["backend_version"] = backend_commit
    context = register_fixture(engine, draft)
    for arm in ("A", "B"):
        run = complete_run(context, arm, final_status="VALID")
        with snapshot_transaction(engine) as connection:
            close_run(connection, draft["campaign_id"], run["run_id"], reason="SOFTWARE_SIMULATION preservation QA")
    failure_draft = campaign_draft()
    for plan in failure_draft["runs"]:
        plan["run"]["versions"]["backend_version"] = backend_commit
    failed = register_fixture(engine, failure_draft)
    for arm, status in (("A", "INVALID"), ("B", "ABORTED")):
        run = complete_run(failed, arm, sequences=(1,), events=False, final_status=status)
        with snapshot_transaction(engine) as connection:
            close_run(connection, failure_draft["campaign_id"], run["run_id"], reason="SOFTWARE_SIMULATION failed attempt retained, not repaired")
    root = directory / "inputs"
    root.mkdir()
    model = b"SOFTWARE_SIMULATION storage reference; not a trained or official Member B model"
    feature_definition = {"data_class": "SOFTWARE_SIMULATION", "names": ["fixture_constant"], "semantics": "stale preservation fixture, not an inferred measurement"}
    feature_sha = digest(encode_evidence(feature_definition))
    policy = encode_evidence({"data_class": "SOFTWARE_SIMULATION", "policy_version": "policy-software-1", "authority": "NOT_MEMBER_D_APPROVAL"})
    artifacts = {
        "model_metadata": ("model-metadata.json", encode_evidence({"data_class": "SOFTWARE_SIMULATION", "models": [{
            "model_version": "model-software-1", "feature_version": "feature-software-1", "artifact_sha256": digest(model),
            "feature_schema_sha256": feature_sha, "feature_definition": feature_definition}]})),
        "policy_metadata": ("policy-metadata.json", encode_evidence({"data_class": "SOFTWARE_SIMULATION", "policies": [{
            "policy_version": "policy-software-1", "artifact_sha256": digest(policy)}]})),
        "model_reference": ("model-reference.bin", model), "policy_reference": ("policy-reference.json", policy),
        "broker_config": ("broker-config.json", encode_evidence({"data_class": "SOFTWARE_SIMULATION", "reference_only": True,
            "acl_source": (Path(__file__).resolve().parents[2] / "infra/mosquitto/acl.conf").read_text()})),
        "backend_config": ("backend-config.json", encode_evidence({"data_class": "SOFTWARE_SIMULATION", "backend_commit": backend_commit,
            "profile": "owned-offline-preservation", "credential_values": "NOT_INCLUDED", "hardware": "NOT_USED"})),
    }
    references = []
    for kind, (name, content) in artifacts.items():
        (root / name).write_bytes(content)
        references.append({"name": name, "kind": kind, "sha256": digest(content)})
    b = draft["runs"][1]["run"]
    with engine.begin() as connection:
        samples = [dict(row) for row in connection.execute(select(telemetry).where(telemetry.c.run_id == b["run_id"]).order_by(telemetry.c.id)).mappings()]
        prediction = PredictionDraft(prediction_id="software-preservation-prediction-" + uuid4().hex,
            device_id=b["device_id"], run_id=b["run_id"], model_version=b["versions"]["model_version"], model_sha256=digest(model),
            feature_version=b["versions"]["feature_version"], feature_schema_sha256=feature_sha, risk_score=0.0, horizon_sec=60,
            max_input_age_sec=1, created_at=utcnow(), input_window_start=context["started"], input_window_end=context["started"] + timedelta(seconds=5),
            input_telemetry_ids=[row["id"] for row in samples])
        saved_prediction = record_prediction(connection, prediction)
        started = monotonic()
        verdict = ShadowVerdict(policy_version=b["versions"]["policy_version"], would_command=None, reason_code="STALE_PREDICTION",
            reason_detail="SOFTWARE_SIMULATION skipped stale storage fixture; elapsed field measures local DTO construction, not D policy/model performance")
        decision = {**verdict.model_dump(mode="json"), "decision_id": "software-preservation-shadow-" + uuid4().hex,
            "prediction_id": prediction.prediction_id, "status": "SKIPPED_STALE", "feature_names": ["fixture_constant"], "feature_values": [0.0]}
        connection.execute(shadow_decisions.insert().values(**decision, payload_sha256=digest(encode_evidence(decision)),
            evaluated_at=utcnow(), policy_duration_ms=(monotonic() - started) * 1000))
    command_rows = []
    for plan in draft["runs"]:
        run = plan["run"]
        command = make_command("software-preservation-command-" + uuid4().hex, device_id=run["device_id"], run_id=run["run_id"],
            controller_id=run["controller_id"], policy_version=run["versions"]["policy_version"], cooling="OFF", duty=None,
            prediction_id=prediction.prediction_id if plan["arm"] == "B" else None, reason_code="SOFTWARE_SIMULATION_STORAGE_FIXTURE")
        intent = create_command_intent(engine, command)
        with engine.begin() as connection:
            pending = cs.begin_publish_attempt(connection, command.command_id, payload_sha256=intent["command"]["payload_sha256"])
            cs.finish_publish_attempt(connection, command.command_id, pending["attempt_id"], outcome="PUBACK",
                broker_reason="SOFTWARE_SIMULATION stored protocol fixture; no MQTT command published")
            ack = make_ack(command.command_id, device_id=run["device_id"], status="DUPLICATE_CANONICAL" if plan["arm"] == "B" else "ACCEPTED",
                boot_id="software-preservation-protocol", applied={"cooling": "OFF", "duty": None}, ack_time=utcnow().isoformat(),
                time_sync_state="UNSYNCHRONIZED", expiry_evaluable=False, reapplied=False,
                reason_code="SOFTWARE_SIMULATION_PROTOCOL_STORAGE_FIXTURE", output_stage="DISABLED", ack_seq=1)
            content = ack_bytes(ack)
            cs.record_ack(connection, topic_device_id=run["device_id"], raw_payload=content.decode(), payload_sha256=digest(content),
                backend_received_at=utcnow(), ack=ack, validity="VALID")
            command_rows.append(cs.get_command(connection, command.command_id))
    command = command_rows[1]
    spec = FrozenModelSpec(model_version=b["versions"]["model_version"], feature_version=b["versions"]["feature_version"],
        artifact_sha256=digest(model), feature_schema_sha256=feature_sha, feature_names=("fixture_constant",), horizon_s=60).model_dump(mode="json")
    with engine.connect() as connection:
        from coldguard_backend.raw_store import telemetry_raw
        raw_hashes = dict(connection.execute(select(telemetry_raw.c.id, telemetry_raw.c.payload_sha256)).all())
    claim = PhysicalClaim(assessment_id="software-preservation-assessment-" + uuid4().hex, authority_id="SOFTWARE_SIMULATION_NOT_A_AUTHORITY",
        command_id=command["command_id"], device_id=b["device_id"], run_id=b["run_id"], origin="SOFTWARE_SIMULATION", stage="VERIFIED",
        reason_code="SOFTWARE_SIMULATION_STORAGE_ONLY", calibration_id="SOFTWARE_SIMULATION", operating_envelope_id="SOFTWARE_SIMULATION_UNCOMMISSIONED",
        window_start=context["started"], window_end=context["started"] + timedelta(seconds=5), assessed_at=utcnow(),
        telemetry_ids=[row["id"] for row in samples], raw_sha256=[raw_hashes[row["raw_id"]] for row in samples])
    # Storage-only positive record: no physical-authority API/signature is used.
    with engine.begin() as connection:
        connection.execute(policy_approvals.insert().values(command_id=command["command_id"], authority_id="SOFTWARE_SIMULATION_NOT_MEMBER_D_APPROVAL",
            policy_version=command["policy_version"], command_sha256=command["payload_sha256"], signature_sha256=digest(b"SOFTWARE_SIMULATION_NOT_A_SIGNATURE"),
            model_spec=spec, model_spec_sha256=digest(encode_evidence(spec)), approved_at=utcnow()))
        connection.execute(physical_assessments.insert().values(assessment_id=claim.assessment_id, command_id=claim.command_id,
            authority_id=claim.authority_id, stage=claim.stage, assessed_at=claim.assessed_at, claim=json.loads(encode_evidence(claim.model_dump())),
            claim_sha256=digest(encode_evidence(claim.model_dump())), signature_sha256=digest(b"SOFTWARE_SIMULATION_NOT_A_PHYSICAL_SIGNATURE")))
        connection.execute(_retired_boot.insert().values(device_id=b["device_id"], boot_id="SOFTWARE_SIMULATION_STORAGE_ONLY_RETIRED_BOOT"))
        legacy_device = "software-preservation-legacy-" + uuid4().hex
        wire = build_telemetry(device_id=legacy_device, boot_id="SOFTWARE_SIMULATION", seq=1, run_id="SOFTWARE_SIMULATION_LEGACY_FIXTURE")
        legacy = store_raw(connection, topic=f"coldguard/{legacy_device}/telemetry", payload=json.dumps(wire).encode(), received_at=context["started"])
        connection.execute(reconciliation_legacy_audit.insert().values(raw_id=legacy["id"], verdict="CONFIRMED_HISTORICAL",
            basis="SOFTWARE_SIMULATION controlled pre-boundary storage fixture, not actual historical campaign acceptance", audited_by="SOFTWARE_SIMULATION"))
    failed_archive = directory / "failed-attempt-archive"
    backup_campaign(engine, failure_draft["campaign_id"], failed_archive, pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
    backup = directory / "populated-source-backup"
    backup_campaign(engine, draft["campaign_id"], backup, pg_dump=os.environ["COLDGUARD_TEST_PG_DUMP"])
    freeze_draft = FreezeDraft(freeze_id="software-preservation-freeze-" + uuid4().hex, campaign_id=draft["campaign_id"],
        created_at=utcnow(), backend_commit=backend_commit, artifacts=references)
    return {**context, "freeze_draft": freeze_draft, "artifact_root": root, "backup": backup, "destination": directory / "frozen",
            "failed_campaign_id": failure_draft["campaign_id"], "failed_archive": failed_archive, "prediction_id": saved_prediction["prediction_id"],
            "command_ids": [row["command_id"] for row in command_rows], "physical_acceptance": "BLOCKED_EXTERNAL"}
