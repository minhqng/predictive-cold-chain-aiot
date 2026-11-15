"""Explicit SOFTWARE_SIMULATION paired fixtures; not real campaign measurements."""

import json
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from coldguard_backend.campaign_store import CampaignCreate, register_campaign
from coldguard_backend.experiment_store import RunCreate, RunTransition, create_run, experiments, transition_run
from coldguard_backend.ingest import ingest_message
from coldguard_backend.simulator import build_event, build_telemetry
from tests.command_testkit import utcnow


@contextmanager
def snapshot_transaction(engine):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            yield connection


def campaign_draft(suffix=None) -> dict:
    suffix = suffix or uuid4().hex
    versions = {"hardware_config_id": "CG-HW-001", "pin_map_version": "SOFTWARE_SIMULATION",
                "firmware_version": "fw-sim-w02", "backend_version": "a" * 40, "schema_version": 1,
                "calibration_id": "SOFTWARE_SIMULATION", "feature_version": "feature-software-1",
                "model_version": "model-software-1", "policy_version": "policy-software-1"}
    return {"campaign_id": "campaign-" + suffix, "data_class": "SOFTWARE_SIMULATION",
            "protocol_version": "software-paired-v1", "validity_rule_reference": "Doc03:6,7,8,85; SOFTWARE_SIMULATION QA only",
            "max_sample_age_sec": 10.0, "runs": [{
                "arm": arm, "run": {"run_id": f"{suffix}-{arm}", "device_id": f"campaign-device-{suffix}",
                    "scenario_id": "S2_DOOR_DISTURBANCE", "controller_id": controller,
                    "pair_id": "pair-" + suffix, "versions": versions.copy(),
                    "notes": "SOFTWARE_SIMULATION: generated paired run, not physical acceptance"},
                "critical_windows": [{"window_id": "primary-event", "start_offset_sec": 1.0,
                    "end_offset_sec": 4.0, "max_gap_sec": 1.1}],
                "required_events": ["DOOR_OPENED", "DOOR_CLOSED"],
            } for arm, controller in (("A", "REACTIVE"), ("B", "PREDICTIVE"))]}


def register_fixture(engine, draft=None) -> dict:
    draft = draft or campaign_draft()
    # Controlled clock fixtures make gap/boundary tests deterministic and avoid sleeping.
    # No data is relabeled as real; timestamps are deliberately software-generated.
    started = utcnow() - timedelta(seconds=30)
    with engine.begin() as connection:
        for plan in draft["runs"]:
            run = RunCreate.model_validate(plan["run"])
            create_run(connection, run)
            connection.execute(experiments.update().where(experiments.c.run_id == run.run_id).values(
                created_at=started - timedelta(seconds=1),
            ))
        campaign = register_campaign(connection, CampaignCreate.model_validate(draft))
    return {"draft": draft, "campaign": campaign, "started": started, "engine": engine}


def start_run(context, arm="A") -> dict:
    plan = next(plan for plan in context["draft"]["runs"] if plan["arm"] == arm)
    run = plan["run"]
    with context["engine"].begin() as connection:
        for status in ("ARMED", "RUNNING"):
            transition_run(connection, run["run_id"], RunTransition(status=status))
        connection.execute(experiments.update().where(experiments.c.run_id == run["run_id"]).values(started_at=context["started"]))
    return run


def send_sample(context, run, seq, **overrides):
    sample = build_telemetry(device_id=run["device_id"], boot_id="software-boot-" + run["run_id"],
                             run_id=run["run_id"], seq=seq, base_time=context["started"])
    sample["calibration_id"] = "SOFTWARE_SIMULATION"
    sample.update(overrides)
    result = ingest_message(context["engine"], topic=f"coldguard/{sample['device_id']}/telemetry",
                            payload=json.dumps(sample).encode(),
                            received_at=context["started"] + timedelta(seconds=seq, milliseconds=50))
    return sample, result


def finish_run(context, run, *, final_status="VALID"):
    with context["engine"].begin() as connection:
        for status in ("COMPLETED_RAW", "VALIDITY_REVIEW", final_status):
            transition_run(connection, run["run_id"], RunTransition(status=status, reason="SOFTWARE_SIMULATION predeclared QA"))
        connection.execute(experiments.update().where(experiments.c.run_id == run["run_id"]).values(
            ended_at=context["started"] + timedelta(seconds=6),
        ))


def complete_run(context, arm="A", *, sequences=(1, 2, 3, 4), events=True, final_status="VALID") -> dict:
    run = start_run(context, arm)
    for seq in sequences:
        send_sample(context, run, seq)
    if events:
        for seq, event_type in ((2, "DOOR_OPENED"), (4, "DOOR_CLOSED")):
            payload = build_event(device_id=run["device_id"], boot_id="software-boot-" + run["run_id"],
                                  seq=seq, run_id=run["run_id"], event_type=event_type, base_time=context["started"])
            ingest_message(context["engine"], topic=f"coldguard/{run['device_id']}/event", payload=json.dumps(payload).encode(),
                            received_at=context["started"] + timedelta(seconds=seq, milliseconds=100))
    finish_run(context, run, final_status=final_status)
    return run
